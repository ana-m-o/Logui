from __future__ import annotations

import logging
import webbrowser
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import (
    Checkbox,
    Input,
    Label,
    ListItem,
    ListView,
    Select,
    Static,
)

from logui.domain.entities.task import Task, TaskLink, TaskNote, TaskStatus
from logui.domain.errors import ValidationError
from logui.domain.ports.tasks import TaskRepository
from logui.ui.dates import fmt_day_full_friendly, fmt_day_short_friendly
from logui.ui.parsing import parse_date_flexible, today_local
from logui.ui.screens.modals import ConfirmScreen
from logui.ui.screens.task_notes import TaskNotesScreen
from logui.usecases.tasks import (
    CreateTaskInput,
    UpdateTaskPatch,
    convert_subtask_to_task,
    convert_task_to_subtask,
    create_subtask,
    create_task,
    cycle_task_status,
    delete_task,
    reposition_task,
    toggle_task_priority,
    update_task,
)

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TaskFormResult:
    title: str
    status: TaskStatus
    priority: bool
    due_date: date | None
    link_url: str
    link_text: str
    repeat: dict[str, Any] | None


_STATUS_OPTIONS: list[tuple[str, str]] = [
    ("todo", "todo"),
    ("in_progress", "in_progress"),
    ("postponed", "postponed"),
    ("in_review", "in_review"),
    ("done", "done"),
]

_REPEAT_FREQ_OPTIONS: list[tuple[str, str]] = [
    ("None", "none"),
    ("Daily", "daily"),
    ("Weekly", "weekly"),
    ("Monthly", "monthly"),
]

_TASK_STATUS_CSS_CLASSES: dict[TaskStatus, str] = {
    TaskStatus.TODO: "task_status_todo",
    TaskStatus.IN_PROGRESS: "task_status_in_progress",
    TaskStatus.POSTPONED: "task_status_postponed",
    TaskStatus.IN_REVIEW: "task_status_in_review",
    TaskStatus.DONE: "task_status_done",
}


def _build_due_date_hint_text(*, due_date_raw: str, today: date) -> str:
    s = (due_date_raw or "").strip()
    if not s:
        return ""

    try:
        due = parse_date_flexible(s, today=today)
    except Exception:  # noqa: BLE001
        return ""

    base = fmt_day_short_friendly(due, today=today)
    if due < today:
        return f"[dim]{base} (is a past date)[/dim]"
    return f"[dim]{base}[/dim]"


def _format_task_notes_block(notes: list[TaskNote], *, depth: int) -> str:
    if not notes:
        return ""
    # Note: indent is handled via TCSS (so we don't introduce big whitespace
    # gaps between widgets).
    return "\n".join(f"- {n.text}" for n in notes)


class TaskFormScreen(ModalScreen[TaskFormResult | None]):
    BINDINGS = [
        Binding("enter", "submit", "Guardar", show=False),
        Binding("escape", "cancel", "Cancelar", show=False),
    ]

    def __init__(self, *, title: str, initial: TaskFormResult):
        super().__init__()
        self._dialog_title = title
        self._initial = initial
        self.add_class("modal")

        # Extract repeat info
        self._current_freq = "none"
        self._current_days_str = ""

        if initial.repeat and isinstance(initial.repeat, dict):
            self._current_freq = initial.repeat.get("freq", "none")
            if self._current_freq == "weekly":
                weekdays = initial.repeat.get("weekdays", [])
                if weekdays:
                    # Convert weekday numbers to abbreviations
                    day_abbr = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
                    self._current_days_str = ", ".join(day_abbr[d] for d in sorted(weekdays))
            elif self._current_freq == "monthly":
                monthdays = initial.repeat.get("monthdays", [])
                if monthdays:
                    self._current_days_str = ", ".join(str(d) for d in sorted(monthdays))

    def compose(self) -> ComposeResult:
        # Determine initial days string if not set
        initial_days_str = self._current_days_str
        if not initial_days_str and self._initial.due_date:
            if self._current_freq == "weekly":
                day_abbr = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
                initial_days_str = day_abbr[self._initial.due_date.weekday()]
            elif self._current_freq == "monthly":
                initial_days_str = str(self._initial.due_date.day)

        yield Container(
            Label(self._dialog_title, id="task_form_title", classes="modal_title"),
            Static(
                "[dim]enter save • esc cancel[/dim]",
                id="task_form_help",
                classes="modal_help",
            ),
            Label("Title *"),
            Input(value=self._initial.title, id="title"),
            Horizontal(
                Container(
                    Label("Status"),
                    Select(
                        _STATUS_OPTIONS,
                        value=self._initial.status.value,
                        id="status",
                    ),
                    classes="half_col",
                ),
                Checkbox(
                    "Priority",
                    value=bool(self._initial.priority),
                    id="priority",
                    classes="no_label_col",
                ),
                classes="modal_row",
            ),
            Horizontal(
                Container(
                    Label("Repeat"),
                    Select(
                        _REPEAT_FREQ_OPTIONS,
                        value=self._current_freq,
                        id="repeat_freq",
                    ),
                    classes="half_col",
                ),
                Container(
                    Label("Days (e.g. mon, wed, fri)"),
                    Input(
                        value=initial_days_str,
                        placeholder="mon, tue, wed, thu, fri, sat, sun",
                        id="repeat_weekdays",
                    ),
                    id="repeat_days_container_weekly",
                    disabled=True,  # Start disabled to prevent rendering issues
                ),
                Container(
                    Label("Days of month (e.g. 1, 15, 30)"),
                    Input(
                        value=initial_days_str,
                        placeholder="1, 15, 30",
                        id="repeat_monthdays",
                    ),
                    id="repeat_days_container_monthly",
                    disabled=True,  # Start disabled to prevent rendering issues
                ),
                classes="modal_row",
            ),
            Label("Due date (optional)"),
            Horizontal(
                Input(
                    value=self._initial.due_date.isoformat() if self._initial.due_date else "",
                    placeholder="2025-12-25, 5/7, 3/6/26 (empty = no due date)",
                    id="due_date",
                ),
                classes="modal_row",
            ),
            Static("", id="due_date_hint", classes="hint hint_primary"),
            Label("Link URL (optional)"),
            Input(
                value=self._initial.link_url,
                placeholder="https://... (empty = no link)",
                id="link_url",
            ),
            Label("Link text (optional)"),
            Input(
                value=self._initial.link_text,
                placeholder="Label to show (optional)",
                id="link_text",
            ),
            Static("", id="task_form_error", classes="modal_error"),
            id="task_form",
            classes="modal_box modal_w80",
        )

    def on_mount(self) -> None:
        self.query_one("#title", Input).focus()
        self._update_due_date_hint()

        self._apply_repeat_freq_ui(self._current_freq)

    def _apply_repeat_freq_ui(self, freq: str) -> None:
        weekly_container = self.query_one("#repeat_days_container_weekly", Container)
        monthly_container = self.query_one("#repeat_days_container_monthly", Container)
        due_date_input = self.query_one("#due_date", Input)

        freq = (freq or "none").strip() or "none"

        # Mirror list behavior: enabling repetition implies having a base date.
        if freq != "none":
            due_raw = (due_date_input.value or "").strip()
            if not due_raw:
                due_date_input.value = today_local().isoformat()
                self._update_due_date_hint()

        if freq == "weekly":
            weekly_container.display = True
            weekly_container.disabled = False
            monthly_container.display = False
            monthly_container.disabled = True

            days_input = weekly_container.query_one("#repeat_weekdays", Input)
            if not (days_input.value or "").strip():
                due_raw = (due_date_input.value or "").strip()
                try:
                    due_date = (
                        parse_date_flexible(due_raw, today=today_local())
                        if due_raw
                        else today_local()
                    )
                except Exception:  # noqa: BLE001
                    due_date = today_local()
                day_abbr = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
                days_input.value = day_abbr[due_date.weekday()]

        elif freq == "monthly":
            weekly_container.display = False
            weekly_container.disabled = True
            monthly_container.display = True
            monthly_container.disabled = False

            days_input = monthly_container.query_one("#repeat_monthdays", Input)
            if not (days_input.value or "").strip():
                due_raw = (due_date_input.value or "").strip()
                try:
                    due_date = (
                        parse_date_flexible(due_raw, today=today_local())
                        if due_raw
                        else today_local()
                    )
                except Exception:  # noqa: BLE001
                    due_date = today_local()
                days_input.value = str(due_date.day)

        else:
            weekly_container.display = False
            weekly_container.disabled = True
            monthly_container.display = False
            monthly_container.disabled = True

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        self._submit()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id in {"due_date"}:
            self._update_due_date_hint()

    @on(Select.Changed, "#repeat_freq")
    def _on_repeat_freq_changed(self, event: Select.Changed) -> None:
        new_freq = str(event.value) if event.value else "none"
        self._apply_repeat_freq_ui(new_freq)

    def _set_hint(self, widget: Static, text: str) -> None:
        cleaned = (text or "").strip()
        widget.update(cleaned)
        if cleaned:
            widget.add_class("is-visible")
        else:
            widget.remove_class("is-visible")

    def _update_due_date_hint(self) -> None:
        hint = self.query_one("#due_date_hint", Static)
        due_raw = (self.query_one("#due_date", Input).value or "").strip()
        self._set_hint(
            hint,
            _build_due_date_hint_text(
                due_date_raw=due_raw,
                today=today_local(),
            ),
        )

    def _submit(self) -> None:
        error = self.query_one("#task_form_error", Static)
        error.update("")

        # Clear all error classes first
        for input_widget in self.query(Input):
            input_widget.remove_class("error")

        title_input = self.query_one("#title", Input)
        due_date_input = self.query_one("#due_date", Input)
        link_url_input = self.query_one("#link_url", Input)
        link_text_input = self.query_one("#link_text", Input)

        title = (title_input.value or "").strip()
        status_raw = self.query_one("#status", Select).value
        priority = bool(self.query_one("#priority", Checkbox).value)

        due_raw = (due_date_input.value or "").strip()
        link_url = (link_url_input.value or "").strip()
        link_text = (link_text_input.value or "").strip()

        errors: list[str] = []

        if not title:
            title_input.add_class("error")
            errors.append("Title cannot be empty")

        status: TaskStatus | None = None
        try:
            if status_raw is None:
                raise ValueError("missing")
            status = TaskStatus(str(status_raw))
        except Exception:  # noqa: BLE001
            errors.append("Invalid status")

        due_date: date | None = None

        if due_raw:
            try:
                due_date = parse_date_flexible(due_raw, today=today_local())
            except Exception:  # noqa: BLE001
                due_date_input.add_class("error")
                errors.append(
                    "Invalid date. Allowed formats: YYYY-MM-DD (2025-12-25), "
                    "DD/MM/YYYY (25/12/2025), DD/MM (5/9), DD/MM/YY (3/6/26), "
                    "MM-DD (12-25) o DD (25)."
                )

        if link_text and not link_url:
            link_url_input.add_class("error")
            errors.append("Link text requires a URL")

        if link_url:
            try:
                TaskLink.create(link_url, text=link_text or None)
            except ValidationError as e:
                link_url_input.add_class("error")
                errors.append(str(e))

        # Build repeat dict
        repeat_freq = str(self.query_one("#repeat_freq", Select).value or "none")
        repeat_dict: dict[str, Any] | None = None

        if repeat_freq and repeat_freq != "none":
            repeat_dict = {"freq": repeat_freq}

            if repeat_freq == "weekly":
                weekly_container = self.query_one("#repeat_days_container_weekly", Container)
                days_input = weekly_container.query_one("#repeat_weekdays", Input)
                days_text = (days_input.value or "").strip().upper()

                if not days_text:
                    errors.append("Weekly repeat requires at least one day (e.g., mon, wed, fri)")
                else:
                    # Parse day abbreviations: mon, tue, wed, thu, fri, sat, sun
                    day_mapping = {
                        "MON": 0,
                        "TUE": 1,
                        "WED": 2,
                        "THU": 3,
                        "FRI": 4,
                        "SAT": 5,
                        "SUN": 6,
                    }
                    parts = [p.strip().upper() for p in days_text.split(",")]
                    weekdays = []
                    for part in parts:
                        if part in day_mapping:
                            weekdays.append(day_mapping[part])
                        else:
                            days_input.add_class("error")
                            errors.append(
                                f"Invalid weekday: {part}. Use mon, tue, wed, thu, fri, sat, sun"
                            )
                            break

                    if weekdays and not errors:
                        repeat_dict["weekdays"] = sorted(set(weekdays))

            elif repeat_freq == "monthly":
                monthly_container = self.query_one("#repeat_days_container_monthly", Container)
                days_input = monthly_container.query_one("#repeat_monthdays", Input)
                days_text = (days_input.value or "").strip()

                if not days_text:
                    errors.append("Monthly repeat requires at least one day (e.g., 1, 15, 30)")
                else:
                    # Parse day numbers: 1-31
                    parts = [p.strip() for p in days_text.split(",")]
                    monthdays = []
                    for part in parts:
                        try:
                            day_num = int(part)
                            if 1 <= day_num <= 31:
                                monthdays.append(day_num)
                            else:
                                days_input.add_class("error")
                                errors.append(f"Day {day_num} must be between 1 and 31")
                                break
                        except ValueError:
                            days_input.add_class("error")
                            errors.append(f"Invalid day number: {part}")
                            break

                    if monthdays and not errors:
                        repeat_dict["monthdays"] = sorted(set(monthdays))

        if errors:
            error.update("[red]" + "\n".join(f"• {m}" for m in errors) + "[/red]")
            return

        self.dismiss(
            TaskFormResult(
                title=title,
                status=status or TaskStatus.TODO,
                priority=priority,
                due_date=due_date,
                link_url=link_url,
                link_text=link_text,
                repeat=repeat_dict,
            )
        )


@dataclass(frozen=True)
class _TaskRow:
    task: Task
    depth: int
    parent_id: UUID | None


def _flatten_task_tree(task: Task, *, depth: int, parent_id: UUID | None) -> list[_TaskRow]:
    rows: list[_TaskRow] = [_TaskRow(task=task, depth=depth, parent_id=parent_id)]
    children = sorted(task.subtasks, key=lambda t: (t.order, t.created_at))
    for st in children:
        rows.extend(_flatten_task_tree(st, depth=depth + 1, parent_id=task.id))
    return rows


class TasksPane(Container):
    BINDINGS = [
        Binding("n", "new", "New", show=False),
        Binding("s", "new_subtask", "Subtask", show=False),
        Binding("enter", "edit", "Edit", show=False, priority=True),
        Binding("e", "edit", "Edit", show=False, priority=True),
        Binding("m", "notes", "Notes", show=False),
        Binding("x", "delete", "Delete", show=False),
        Binding("c", "cycle_status", "Cycle status", show=False),
        Binding("p", "toggle_priority", "Priority", show=False),
        Binding("r", "cycle_repeat", "Repeat", show=False),
        Binding("o", "open_link", "Open link", show=False),
        Binding("i", "indent", "Indent", show=False),
        Binding("u", "unindent", "Unindent", show=False),
        Binding("alt+up", "move_up", "Move up", show=False),
        Binding("alt+down", "move_down", "Move down", show=False),
    ]

    def __init__(self, repo: TaskRepository):
        super().__init__(id="tasks")
        self._repo = repo
        self._rows: list[_TaskRow] = []
        self._tasks_to_hide: dict[UUID, float] = {}  # task_id -> timestamp when marked DONE

    def compose(self) -> ComposeResult:
        yield Container(
            Horizontal(
                Label("Tasks"),
                classes="page_header",
            ),
            Static(
                "[dim]n new • s subtask • m notes • e/enter edit • x delete • c status • "
                "p priority • r repeat • o open link • i indent • u unindent • alt+↑/↓ reorder[/dim]",
                classes="page_help",
            ),
            ListView(id="tasks_list", classes="task_list"),
        )

    def on_mount(self) -> None:
        self._refresh()
        # Start polling for auto-hide checks
        try:
            self.set_interval(15, self._check_auto_hide_tasks)
        except Exception:  # noqa: BLE001
            pass

    def on_day_rollover(self, *, today: date) -> None:
        selected = self._selected_task()
        keep_id = str(selected.id) if selected is not None else None
        self._refresh(keep_id=keep_id, keep_scroll=True, focus=False, today=today)

    def _notify(self, message: str) -> None:
        notify = getattr(self.app, "notify", None)
        if callable(notify):
            notify(message)

    def _refresh(
        self,
        *,
        keep_id: str | None = None,
        keep_scroll: bool = False,
        focus: bool = True,
        today: date | None = None,
    ) -> None:
        lv = self.query_one("#tasks_list", ListView)
        had_focus = lv.has_focus
        old_scroll_y: int | None = None
        if keep_scroll:
            old_scroll_y = getattr(lv, "scroll_y", None)

        # Optimization: Don't fetch DONE tasks from previous days (we filter them anyway)
        roots = list(self._repo.list_tasks(include_old_completed=False))
        roots.sort(key=lambda t: (t.order, t.created_at))

        rows: list[_TaskRow] = []
        for t in roots:
            rows.extend(_flatten_task_tree(t, depth=0, parent_id=None))

        today = today or today_local()

        # Check if auto-hide is enabled
        auto_hide_enabled = False
        try:
            from logui.domain.ports.config import ConfigRepository

            config_repo = getattr(self.app, "_config_repo", None)
            if config_repo and isinstance(config_repo, ConfigRepository):
                config = config_repo.load()
                auto_hide_enabled = config.ui.auto_hide_completed
        except Exception:  # noqa: BLE001
            pass

        # Filter tasks:
        # - Hide DONE tasks from previous days (keep only completed today)
        # - If auto_hide_enabled, also hide DONE tasks from today
        # - For tasks with recurrence and due_date, check if they occur on/after today
        filtered_rows: list[_TaskRow] = []
        for row in rows:
            task = row.task

            # Hide DONE tasks based on completion date and auto_hide setting
            if task.status == TaskStatus.DONE:
                completed = task.completed_at or task.updated_at
                done_day = completed.astimezone().date()
                if done_day < today:
                    continue
                if done_day == today and auto_hide_enabled:
                    continue

            # For tasks with recurrence and due_date, check if they're still active
            if task.repeat and isinstance(task.repeat, dict) and task.due_date:
                freq = task.repeat.get("freq")
                if freq and freq != "none":
                    # Check if recurrence is still active
                    until = task.repeat.get("until")
                    if until is not None:
                        # Has 'until' date, check if we're past it
                        if isinstance(until, str):
                            from datetime import datetime

                            try:
                                until_date = datetime.fromisoformat(until).date()
                                if today > until_date:
                                    continue
                            except Exception:  # noqa: BLE001
                                pass
                        elif isinstance(until, date):
                            if today > until:
                                continue

            filtered_rows.append(row)

        self._rows = filtered_rows

        lv.clear()

        if not self._rows:
            lv.append(ListItem(Label("(No tasks) — press n to create one")))
            if focus or had_focus:
                lv.focus()
            return

        selected_idx = 0
        if keep_id:
            for idx, row in enumerate(self._rows):
                if str(row.task.id) == keep_id:
                    selected_idx = idx
                    break

        for row in self._rows:
            lv.append(self._build_list_item(row))

        lv.index = None
        lv.index = selected_idx
        if old_scroll_y is not None:
            try:
                lv.scroll_y = old_scroll_y
            except Exception as e:  # noqa: BLE001
                _log.debug("Failed restoring tasks scroll position: %s", e)

        if focus or had_focus:
            lv.focus()

    def _status_tag(self, status: TaskStatus) -> str:
        return {
            TaskStatus.TODO: "[ ]",
            TaskStatus.IN_PROGRESS: "[/]",
            TaskStatus.POSTPONED: "[>]",
            TaskStatus.IN_REVIEW: "[R]",
            TaskStatus.DONE: "[X]",
        }.get(status, "[?]")

    def _status_label(self, status: TaskStatus) -> str:
        # User-facing label for notifications.
        return str(status.value).replace("_", " ").title()

    def _fmt_day(self, day: date) -> str:
        return fmt_day_full_friendly(day)

    def _apply_task_status_classes(self, item: ListItem, status: TaskStatus) -> None:
        for css_class in _TASK_STATUS_CSS_CLASSES.values():
            item.remove_class(css_class)

        item.add_class(_TASK_STATUS_CSS_CLASSES.get(status, "task_status_todo"))

        if status == TaskStatus.DONE:
            item.add_class("task_done")
        else:
            item.remove_class("task_done")

    def _apply_task_priority_classes(self, item: ListItem, priority: bool) -> None:
        if priority:
            item.add_class("task_is_priority")
        else:
            item.remove_class("task_is_priority")

    def _apply_task_due_classes(
        self,
        item: ListItem,
        due_date: date | None,
        *,
        today: date,
    ) -> None:
        if due_date is not None and due_date <= today:
            item.add_class("task_due_today_or_past")
        else:
            item.remove_class("task_due_today_or_past")

    def _build_list_item(self, row: _TaskRow) -> ListItem:
        t = row.task
        depth = row.depth
        today = today_local()
        pri_text = "✱" if t.priority else " "
        priority = Static(pri_text, markup=False, classes="task_priority")
        status = Static(self._status_tag(t.status), markup=False, classes="task_status")

        title = Static(t.title, markup=False, classes="task_title")

        due = ""
        if t.due_date is not None:
            due = f"  ({self._fmt_day(t.due_date)})"
        due_w = Static(due, markup=False, classes="task_due")
        if t.due_date is not None and t.due_date < today:
            due_w.add_class("is_overdue")

        link_text = ""
        if t.link is not None:
            link_text = t.link.display_text()
        link_w = Static(link_text, markup=False, classes="task_link")

        # Repeat indicator
        repeat_text = ""
        if t.repeat and isinstance(t.repeat, dict):
            freq = str(t.repeat.get("freq") or "")
            if freq and freq != "none":
                if freq == "daily":
                    repeat_text = " 🔁 daily"
                elif freq == "weekly":
                    if t.due_date:
                        day_name = t.due_date.strftime("%A").lower()
                        repeat_text = f" 🔁 {day_name}"
                    else:
                        repeat_text = " 🔁 weekly"
                elif freq == "monthly":
                    if t.due_date:
                        day_num = t.due_date.day
                        repeat_text = f" 🔁 day {day_num}"
                    else:
                        repeat_text = " 🔁 monthly"
                else:
                    repeat_text = " 🔁"
        repeat_w = Static(repeat_text, markup=False, classes="task_repeat")

        row_widget = Horizontal(
            priority, status, title, link_w, repeat_w, due_w, classes="task_list_row"
        )

        notes_block = _format_task_notes_block(t.notes or [], depth=depth)
        notes_w = Static(notes_block, classes="task_row_notes", markup=False)
        if notes_block:
            notes_w.add_class("is-visible")

        item = ListItem(
            Container(
                row_widget,
                notes_w,
                classes="task_row",
            )
        )

        if depth > 0:
            item.add_class("task_subtask")
        self._apply_task_status_classes(item, t.status)
        self._apply_task_priority_classes(item, t.priority)
        self._apply_task_due_classes(item, t.due_date, today=today)
        return item

    def _selected_task(self) -> Task | None:
        if not self._rows:
            return None
        lv = self.query_one("#tasks_list", ListView)
        idx = lv.index or 0
        if idx < 0 or idx >= len(self._rows):
            return None
        return self._rows[idx].task

    def _selected_row(self) -> _TaskRow | None:
        if not self._rows:
            return None
        lv = self.query_one("#tasks_list", ListView)
        idx = lv.index or 0
        if idx < 0 or idx >= len(self._rows):
            return None
        return self._rows[idx]

    def _selected_index(self) -> int | None:
        if not self._rows:
            return None
        lv = self.query_one("#tasks_list", ListView)
        idx = lv.index or 0
        if idx < 0 or idx >= len(self._rows):
            return None
        return idx

    def _remove_task_from_list(self, task_id: UUID) -> None:
        """Remove a task from the ListView without refreshing the entire list."""
        try:
            lv = self.query_one("#tasks_list", ListView)

            # Find the index of the task in _rows
            idx = next((i for i, row in enumerate(self._rows) if row.task.id == task_id), None)
            if idx is None:
                return

            # Remove from internal list
            self._rows.pop(idx)

            # Get the ListItem and remove it (like move_child does)
            items = list(lv.query(ListItem))
            if idx < len(items):
                item_to_remove = items[idx]
                item_to_remove.remove()
                self._notify("Task archived")

                # Notify LogPane to refresh so archived tasks appear immediately
                try:
                    from logui.ui.screens.log import LogPane

                    try:
                        log_pane = self.app.query_one(LogPane)
                    except Exception:  # noqa: BLE001
                        log_pane = None

                    if log_pane is not None:
                        try:
                            log_pane.refresh_log()
                        except Exception:  # noqa: BLE001
                            pass
                except Exception:  # noqa: BLE001
                    pass

            # If list is now empty, show the empty message
            if not self._rows:
                lv.clear()
                lv.append(ListItem(Label("(No tasks) — press n to create one")))

        except Exception:  # noqa: BLE001
            # Fallback to full refresh if something goes wrong
            self._refresh()

    def _check_auto_hide_tasks(self) -> None:
        """Polling method to check and hide tasks that should be removed."""
        # Check if auto-hide is enabled
        auto_hide_enabled = False
        try:
            from logui.usecases.config import ConfigRepository

            config_repo = getattr(self.app, "_config_repo", None)
            if config_repo and isinstance(config_repo, ConfigRepository):
                config = config_repo.load()
                auto_hide_enabled = config.ui.auto_hide_completed
        except Exception:  # noqa: BLE001
            pass

        if not auto_hide_enabled:
            self._tasks_to_hide.clear()
            return

        # Check tasks that need to be hidden
        import time

        now = time.time()
        tasks_to_remove = []

        for task_id, marked_time in list(self._tasks_to_hide.items()):
            if now - marked_time >= 5.0:
                tasks_to_remove.append(task_id)

        # Remove tasks
        for task_id in tasks_to_remove:
            try:
                # Verify task still exists and is DONE before removing from UI
                task = None
                try:
                    task = self._repo.get_task(task_id)
                except Exception:  # noqa: BLE001
                    task = None

                if task is None or task.status == TaskStatus.DONE:
                    self._remove_task_from_list(task_id)
                    self._tasks_to_hide.pop(task_id, None)
                else:
                    # Task changed state since scheduling; do not archive.
                    self._tasks_to_hide.pop(task_id, None)
            except Exception:  # noqa: BLE001
                # Ensure we don't leave stale entries or crash; fall back to refresh
                self._tasks_to_hide.pop(task_id, None)
                try:
                    self._refresh()
                except Exception:
                    pass

    def _update_selected_item_in_place(self, updated: Task, *, focus: bool = True) -> None:
        idx = self._selected_index()
        if idx is None:
            return

        lv = self.query_one("#tasks_list", ListView)
        items = list(lv.query(ListItem))
        if idx >= len(items):
            self._refresh(keep_id=str(updated.id))
            return

        item = items[idx]
        try:
            item.query_one(".task_priority", Static).update("✱" if updated.priority else " ")
            self._apply_task_priority_classes(item, updated.priority)
            item.query_one(".task_status", Static).update(self._status_tag(updated.status))
            item.query_one(".task_title", Static).update(updated.title)

            due = ""
            if updated.due_date is not None:
                due = f"  ({self._fmt_day(updated.due_date)})"
            due_w = item.query_one(".task_due", Static)
            due_w.update(due)
            today = today_local()
            if updated.due_date is not None and updated.due_date < today:
                due_w.add_class("is_overdue")
            else:
                due_w.remove_class("is_overdue")
            self._apply_task_due_classes(item, updated.due_date, today=today)

            link_text = ""
            if updated.link is not None:
                link_text = updated.link.display_text()
            item.query_one(".task_link", Static).update(link_text)

            # Update repeat indicator
            repeat_text = ""
            if updated.repeat and isinstance(updated.repeat, dict):
                freq = str(updated.repeat.get("freq") or "")
                if freq and freq != "none":
                    if freq == "daily":
                        repeat_text = " 🔁 daily"
                    elif freq == "weekly":
                        if updated.due_date:
                            day_name = updated.due_date.strftime("%A").lower()
                            repeat_text = f" 🔁 {day_name}"
                        else:
                            repeat_text = " 🔁 weekly"
                    elif freq == "monthly":
                        if updated.due_date:
                            day_num = updated.due_date.day
                            repeat_text = f" 🔁 day {day_num}"
                        else:
                            repeat_text = " 🔁 monthly"
                    else:
                        repeat_text = " 🔁"
            item.query_one(".task_repeat", Static).update(repeat_text)
            self._apply_task_status_classes(item, updated.status)

            depth = self._rows[idx].depth
            notes_block = _format_task_notes_block(updated.notes or [], depth=depth)
            notes_w = item.query_one(".task_row_notes", Static)
            notes_w.update(notes_block)
            if (notes_block or "").strip():
                notes_w.add_class("is-visible")
            else:
                notes_w.remove_class("is-visible")
        except Exception:  # noqa: BLE001
            self._refresh(keep_id=str(updated.id))
            return

        self._rows[idx] = _TaskRow(
            task=updated,
            depth=self._rows[idx].depth,
            parent_id=self._rows[idx].parent_id,
        )
        lv.index = idx
        if focus:
            lv.focus()

    def action_notes(self) -> None:
        task = self._selected_task()
        if task is None:
            return

        def _on_changed(updated: Task) -> None:
            # Update underlying list without stealing focus from the modal.
            self._update_selected_item_in_place(updated, focus=False)

        def _on_dismiss(_result: object) -> None:
            # Restore focus to the tasks list.
            self.query_one("#tasks_list", ListView).focus()

        self.app.push_screen(
            TaskNotesScreen(self._repo, task.id, on_changed=_on_changed),
            callback=_on_dismiss,
        )

    def action_new_subtask(self) -> None:
        parent = self._selected_task()
        if parent is None:
            return

        initial = TaskFormResult(
            title="",
            status=TaskStatus.TODO,
            priority=False,
            due_date=None,
            link_url="",
            link_text="",
            repeat=None,
        )
        screen = TaskFormScreen(title="New subtask", initial=initial)
        parent_id = parent.id

        def _on_dismiss(result: TaskFormResult | None) -> None:
            if result is None:
                return
            try:
                t = create_subtask(
                    self._repo,
                    parent_id,
                    CreateTaskInput(
                        title=result.title,
                        status=result.status,
                        priority=result.priority,
                        due_date=result.due_date,
                        link=TaskLink.create(result.link_url, text=result.link_text or None)
                        if result.link_url
                        else None,
                    ),
                )
                # Note: Subtasks cannot have recurrence, so we don't assign result.repeat
                self._refresh(keep_id=str(t.id))
                self._notify("Subtask created")
            except ValidationError as e:
                self._notify(f"Error: {e}")

        self.app.push_screen(screen, callback=_on_dismiss)

    def action_new(self) -> None:
        initial = TaskFormResult(
            title="",
            status=TaskStatus.TODO,
            priority=False,
            due_date=None,
            link_url="",
            link_text="",
            repeat=None,
        )
        screen = TaskFormScreen(title="New task", initial=initial)

        def _on_dismiss(result: TaskFormResult | None) -> None:
            if result is None:
                return
            try:
                t = create_task(
                    self._repo,
                    CreateTaskInput(
                        title=result.title,
                        status=result.status,
                        priority=result.priority,
                        due_date=result.due_date,
                        link=TaskLink.create(result.link_url, text=result.link_text or None)
                        if result.link_url
                        else None,
                    ),
                )
                # Assign repeat field if provided
                if result.repeat:
                    t.repeat = result.repeat
                    self._repo.upsert_task(t)
                self._refresh(keep_id=str(t.id))
                self._notify("Task created")
            except ValidationError as e:
                self._notify(f"Error: {e}")

        self.app.push_screen(screen, callback=_on_dismiss)

    def action_edit(self) -> None:
        task = self._selected_task()
        if task is None:
            return

        initial = TaskFormResult(
            title=task.title,
            status=task.status,
            priority=task.priority,
            due_date=task.due_date,
            link_url=task.link.url if task.link else "",
            link_text=task.link.text or "" if task.link else "",
            repeat=task.repeat,
        )
        screen = TaskFormScreen(title="Edit task", initial=initial)

        def _on_dismiss(result: TaskFormResult | None) -> None:
            if result is None:
                return
            try:
                # Save previous status to check if task was just marked as DONE
                previous_status = task.status

                updated = update_task(
                    self._repo,
                    task.id,
                    UpdateTaskPatch(
                        title=result.title,
                        status=result.status,
                        priority=result.priority,
                        due_date=result.due_date,
                        link=TaskLink.create(result.link_url, text=result.link_text or None)
                        if result.link_url
                        else None,
                    ),
                )
                # Update repeat field separately
                updated.repeat = result.repeat
                self._repo.upsert_task(updated)
                self._update_selected_item_in_place(updated)

                # Check if auto-hide is enabled and task was just marked as DONE
                auto_hide_enabled = False
                try:
                    from logui.usecases.config import ConfigRepository

                    config_repo = getattr(self.app, "_config_repo", None)
                    if config_repo and isinstance(config_repo, ConfigRepository):
                        config = config_repo.load()
                        auto_hide_enabled = config.ui.auto_hide_completed
                except Exception:  # noqa: BLE001
                    pass

                # If marked as DONE and auto-hide is enabled, schedule removal
                if (
                    updated.status == TaskStatus.DONE
                    and previous_status != TaskStatus.DONE
                    and auto_hide_enabled
                ):
                    import time

                    task_id = updated.id
                    # Record timestamp for polling-based removal
                    self._tasks_to_hide[task_id] = time.time()
                    self._notify("Task updated (will archive in a few seconds)")
                else:
                    self._notify("Task updated")
            except ValidationError as e:
                self._notify(f"Error: {e}")

        self.app.push_screen(screen, callback=_on_dismiss)

    def action_delete(self) -> None:
        task = self._selected_task()
        if task is None:
            return

        title = task.title

        def _on_confirm(ok: bool) -> None:
            if not ok:
                return
            delete_task(self._repo, task.id)
            self._refresh()
            self._notify("Task deleted")

        self.app.push_screen(ConfirmScreen(f"Delete task '{title}'?"), callback=_on_confirm)

    def action_cycle_status(self) -> None:
        task = self._selected_task()
        if task is None:
            return
        try:
            # Check if this is a recurring task that might clone
            will_clone = (
                task.status != TaskStatus.DONE
                and task.repeat
                and isinstance(task.repeat, dict)
                and task.repeat.get("freq")
                and task.repeat.get("freq") != "none"
            )

            # Check if task is being marked as DONE
            will_be_done = task.status != TaskStatus.DONE

            updated = cycle_task_status(self._repo, task.id)

            # Check if auto-hide is enabled
            auto_hide_enabled = False
            try:
                from logui.usecases.config import ConfigRepository

                config_repo = getattr(self.app, "_config_repo", None)
                if config_repo and isinstance(config_repo, ConfigRepository):
                    config = config_repo.load()
                    auto_hide_enabled = config.ui.auto_hide_completed
            except Exception:  # noqa: BLE001
                pass

            # If marked as DONE and it was recurring, refresh the whole list
            # (a new task may have been cloned)
            if updated.status == TaskStatus.DONE and will_clone:
                self._refresh(keep_id=str(updated.id))
            else:
                self._update_selected_item_in_place(updated)

            # If marked as DONE and auto-hide is enabled, schedule removal
            if updated.status == TaskStatus.DONE and will_be_done and auto_hide_enabled:
                task_id = updated.id
                # Record timestamp for polling-based removal
                import time

                self._tasks_to_hide[task_id] = time.time()
                self._notify(
                    f"Task status: {self._status_label(updated.status)} (will archive in a few seconds)"
                )
            else:
                self._notify(f"Task status: {self._status_label(updated.status)}")
        except ValidationError as e:
            self._notify(f"Error: {e}")

    def action_toggle_priority(self) -> None:
        task = self._selected_task()
        if task is None:
            return
        try:
            updated = toggle_task_priority(self._repo, task.id)
            self._update_selected_item_in_place(updated)
        except ValidationError as e:
            self._notify(f"Error: {e}")

    def action_cycle_repeat(self) -> None:
        """Cycle through repeat frequencies (none → daily → weekly → monthly)."""
        selected_row = self._selected_row()
        if selected_row is None:
            return

        # Subtasks cannot have independent repetition
        if selected_row.depth > 0:
            self._notify("Las subtareas no pueden tener repetición independiente")
            return

        task = selected_row.task

        try:
            from logui.usecases import cycle_task_repeat

            updated = cycle_task_repeat(self._repo, task.id)
            self._update_selected_item_in_place(updated)

            # Show current frequency
            freq = "ninguna"
            if updated.repeat and isinstance(updated.repeat, dict):
                f = updated.repeat.get("freq", "none")
                if f == "daily":
                    freq = "diaria"
                elif f == "weekly":
                    freq = "semanal"
                elif f == "monthly":
                    freq = "mensual"

            self._notify(f"Repetición: {freq}")
        except ValidationError as e:
            self._notify(f"Error: {e}")

    def action_open_link(self) -> None:
        task = self._selected_task()
        if task is None or task.link is None:
            return

        try:
            webbrowser.open(task.link.url)
        except Exception as e:  # noqa: BLE001
            self._notify(f"Error opening link: {e}")

    def _handle_link_click(self, event: events.Click) -> bool:
        if event.button != 1:
            return False

        # If the click is on the link widget (or a child), open the URL.
        w = event.widget
        while w is not None:
            has_class = getattr(w, "has_class", None)
            if callable(has_class) and w.has_class("task_link"):
                break
            w = getattr(w, "parent", None)
        if w is None:
            return False

        li = event.widget
        while li is not None and not isinstance(li, ListItem):
            li = getattr(li, "parent", None)
        if li is None:
            return False

        list_view = getattr(li, "parent", None)
        while list_view is not None and not isinstance(list_view, ListView):
            list_view = getattr(list_view, "parent", None)
        if list_view is None:
            return False

        if getattr(list_view, "id", None) != "tasks_list":
            return False

        items = list(list_view.query(ListItem))
        try:
            idx = items.index(li)
        except ValueError:
            return False
        if idx < 0 or idx >= len(self._rows):
            return False

        list_view.index = idx
        list_view.focus()

        task = self._rows[idx].task
        if task.link is None:
            return True

        try:
            webbrowser.open(task.link.url)
        except Exception as e:  # noqa: BLE001
            self._notify(f"Error opening link: {e}")
        return True

    def action_move_up(self) -> None:
        self._move_selected_in_place(direction=-1)

    def action_move_down(self) -> None:
        self._move_selected_in_place(direction=+1)

    def _move_selected_in_place(self, *, direction: int) -> None:
        if direction not in (-1, +1):
            raise ValueError("direction must be -1 or +1")

        selected = self._selected_row()
        if selected is None:
            return

        task = selected.task

        lv = self.query_one("#tasks_list", ListView)
        idx = lv.index or 0

        # Determine current subtree block [start, end]
        cur_start = idx
        cur_end = idx
        for j in range(idx + 1, len(self._rows)):
            if self._rows[j].depth <= selected.depth:
                break
            cur_end = j

        if direction == -1:
            prev_start: int | None = None
            for j in range(cur_start - 1, -1, -1):
                if self._rows[j].depth < selected.depth:
                    break
                if (
                    self._rows[j].depth == selected.depth
                    and self._rows[j].parent_id == selected.parent_id
                ):
                    prev_start = j
                    break
            if prev_start is None:
                lv.focus()
                return
            neighbor_start = prev_start
            neighbor_end = cur_start - 1
        else:
            next_start: int | None = None
            for j in range(cur_end + 1, len(self._rows)):
                if self._rows[j].depth < selected.depth:
                    break
                if (
                    self._rows[j].depth == selected.depth
                    and self._rows[j].parent_id == selected.parent_id
                ):
                    next_start = j
                    break
            if next_start is None:
                lv.focus()
                return
            next_end = next_start
            for j in range(next_start + 1, len(self._rows)):
                if self._rows[j].depth <= selected.depth:
                    break
                next_end = j
            neighbor_start = next_start
            neighbor_end = next_end

        after_task_id: UUID | None = None
        before_task_id: UUID | None = None
        if direction == -1:
            before_task_id = self._rows[neighbor_start].task.id
            prev_visible_same_level: UUID | None = None
            for j in range(neighbor_start - 1, -1, -1):
                row = self._rows[j]
                if row.depth < selected.depth:
                    break
                if row.depth == selected.depth and row.parent_id == selected.parent_id:
                    prev_visible_same_level = row.task.id
                    break
            after_task_id = prev_visible_same_level
        else:
            after_task_id = self._rows[neighbor_start].task.id
            next_visible_same_level: UUID | None = None
            for j in range(neighbor_end + 1, len(self._rows)):
                row = self._rows[j]
                if row.depth < selected.depth:
                    break
                if row.depth == selected.depth and row.parent_id == selected.parent_id:
                    next_visible_same_level = row.task.id
                    break
            before_task_id = next_visible_same_level

        try:
            updated = reposition_task(
                self._repo,
                task.id,
                after_task_id=after_task_id,
                before_task_id=before_task_id,
            )
        except ValidationError as e:
            self._notify(f"Error: {e}")
            lv.focus()
            return

        # Keep visible UI updates in-place (no full refresh) to avoid flicker.
        task.order = updated.order

        # Update in-memory rows by swapping whole root/subtree blocks.
        cur_block = self._rows[cur_start : cur_end + 1]
        neighbor_block = self._rows[neighbor_start : neighbor_end + 1]
        if direction == -1:
            self._rows = (
                self._rows[:neighbor_start] + cur_block + neighbor_block + self._rows[cur_end + 1 :]
            )
        else:
            self._rows = (
                self._rows[:cur_start] + neighbor_block + cur_block + self._rows[neighbor_end + 1 :]
            )

        items = list(lv.query(ListItem))
        if cur_end >= len(items) or neighbor_end >= len(items):
            self._refresh(keep_id=str(task.id), keep_scroll=True, focus=True)
            return

        if direction == -1:
            anchor = items[neighbor_start]
            for li in items[cur_start : cur_end + 1]:
                lv.move_child(li, before=anchor)
        else:
            anchor = items[neighbor_end]
            for li in reversed(items[cur_start : cur_end + 1]):
                lv.move_child(li, after=anchor)

        for new_idx, r in enumerate(self._rows):
            if r.task.id == task.id:
                lv.index = new_idx
                break
        lv.focus()

    def action_indent(self) -> None:
        """Convert selected task into a subtask of the task above it."""
        selected_row = self._selected_row()
        if selected_row is None:
            return

        task = selected_row.task
        lv = self.query_one("#tasks_list", ListView)
        idx = lv.index or 0

        # Cannot indent first item
        if idx == 0:
            self._notify("Cannot indent: already at top")
            lv.focus()
            return

        # Cannot indent if already a subtask (only 1 level allowed)
        if selected_row.depth > 0:
            self._notify("Cannot indent: already a subtask")
            lv.focus()
            return

        # Cannot indent if task has subtasks (to maintain single level)
        if task.subtasks:
            self._notify("Cannot indent: task has subtasks")
            lv.focus()
            return

        # Find the task above
        prev_row = self._rows[idx - 1]
        target_parent_row = prev_row

        # If prev row is a subtask, find its parent (the root task)
        if prev_row.depth > 0:
            # Search backwards for the parent
            for j in range(idx - 2, -1, -1):
                if self._rows[j].depth == 0:
                    target_parent_row = self._rows[j]
                    break

        target_parent_id = target_parent_row.task.id

        # Perform the conversion
        try:
            convert_task_to_subtask(self._repo, task.id, target_parent_id)
            self._indent_selected_in_place(task.id, idx)
            self._notify("Task converted to subtask")
        except ValidationError as e:
            self._notify(f"Error: {e}")
            lv.focus()

    def _indent_selected_in_place(self, task_id: UUID, old_idx: int) -> None:
        """Update the list after indenting a task, without full refresh."""
        lv = self.query_one("#tasks_list", ListView)
        
        # Recalculate rows from repository
        roots = list(self._repo.list_tasks(include_old_completed=False))
        roots.sort(key=lambda t: (t.order, t.created_at))
        new_rows: list[_TaskRow] = []
        for t in roots:
            new_rows.extend(_flatten_task_tree(t, depth=0, parent_id=None))
        
        # Find where the task ended up
        new_idx = next((i for i, row in enumerate(new_rows) if row.task.id == task_id), None)
        if new_idx is None:
            # Fallback to full refresh if we can't find it
            self._refresh(keep_id=str(task_id), focus=True)
            return
        
        # Update internal rows
        self._rows = new_rows
        
        # Remove the old item
        items = list(lv.query(ListItem))
        if old_idx < len(items):
            items[old_idx].remove()
        
        # Build the new item (now with indentation)
        new_item = self._build_list_item(new_rows[new_idx])
        
        # Insert at the correct position
        remaining_items = list(lv.query(ListItem))
        if new_idx == 0:
            if len(remaining_items) > 0:
                lv.mount(new_item, before=remaining_items[0])
            else:
                lv.mount(new_item)
        elif new_idx >= len(remaining_items):
            lv.mount(new_item)
        else:
            lv.mount(new_item, before=remaining_items[new_idx])
        
        # Update selection
        lv.index = new_idx
        lv.focus()

    def action_unindent(self) -> None:
        """Convert selected subtask into a root task."""
        selected_row = self._selected_row()
        if selected_row is None:
            return

        task = selected_row.task
        lv = self.query_one("#tasks_list", ListView)
        old_idx = lv.index or 0

        # Cannot unindent if already a root task
        if selected_row.depth == 0:
            self._notify("Cannot unindent: already a root task")
            lv.focus()
            return

        # Perform the conversion
        try:
            convert_subtask_to_task(self._repo, task.id)
            self._unindent_selected_in_place(task.id, old_idx)
            self._notify("Subtask converted to task")
        except ValidationError as e:
            self._notify(f"Error: {e}")
            lv.focus()

    def _unindent_selected_in_place(self, task_id: UUID, old_idx: int) -> None:
        """Update the list after unindenting a task, without full refresh."""
        lv = self.query_one("#tasks_list", ListView)
        
        # Recalculate rows from repository
        roots = list(self._repo.list_tasks(include_old_completed=False))
        roots.sort(key=lambda t: (t.order, t.created_at))
        new_rows: list[_TaskRow] = []
        for t in roots:
            new_rows.extend(_flatten_task_tree(t, depth=0, parent_id=None))
        
        # Find where the task ended up
        new_idx = next((i for i, row in enumerate(new_rows) if row.task.id == task_id), None)
        if new_idx is None:
            # Fallback to full refresh if we can't find it
            self._refresh(keep_id=str(task_id), focus=True)
            return
        
        # Update internal rows
        self._rows = new_rows
        
        # Remove the old item
        items = list(lv.query(ListItem))
        if old_idx < len(items):
            items[old_idx].remove()
        
        # Build the new item (now without indentation)
        new_item = self._build_list_item(new_rows[new_idx])
        
        # Insert at the correct position
        remaining_items = list(lv.query(ListItem))
        if new_idx == 0:
            if len(remaining_items) > 0:
                lv.mount(new_item, before=remaining_items[0])
            else:
                lv.mount(new_item)
        elif new_idx >= len(remaining_items):
            lv.mount(new_item)
        else:
            lv.mount(new_item, before=remaining_items[new_idx])
        
        # Update selection
        lv.index = new_idx
        lv.focus()

    def on_click(self, event: events.Click) -> None:
        if self._handle_link_click(event):
            return

        if event.chain < 2 or event.button != 1:
            return

        w = event.widget
        while w is not None and not isinstance(w, ListItem):
            w = getattr(w, "parent", None)
        if w is None:
            return

        list_view = getattr(w, "parent", None)
        while list_view is not None and not isinstance(list_view, ListView):
            list_view = getattr(list_view, "parent", None)
        if list_view is None:
            return

        if getattr(list_view, "id", None) != "tasks_list":
            return

        list_view.focus()
        self.call_later(self.action_edit)
