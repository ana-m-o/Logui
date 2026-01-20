from __future__ import annotations

import webbrowser
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from textual import events
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
from logui.ui.dates import fmt_day_full_friendly
from logui.ui.screens.events import fmt_day_short_friendly, parse_date_flexible, today_local
from logui.ui.screens.modals import ConfirmScreen
from logui.ui.screens.task_notes import TaskNotesScreen
from logui.usecases.tasks import (
    CreateTaskInput,
    UpdateTaskPatch,
    create_subtask,
    create_task,
    cycle_task_status,
    delete_task,
    move_task_down,
    move_task_up,
    toggle_task_priority,
    update_task,
)


@dataclass(frozen=True)
class TaskFormResult:
    title: str
    status: TaskStatus
    priority: bool
    due_date: date | None
    link_url: str
    link_text: str


_STATUS_OPTIONS: list[tuple[str, str]] = [
    ("todo", "todo"),
    ("in_progress", "in_progress"),
    ("postponed", "postponed"),
    ("in_review", "in_review"),
    ("done", "done"),
]


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

    def compose(self) -> ComposeResult:
        yield Container(
            Label(self._dialog_title, id="task_form_title", classes="modal_title"),
            Static(
                "[dim]enter save • esc cancel[/dim]",
                id="task_form_help",
                classes="modal_help",
            ),
            Label("Title *"),
            Input(value=self._initial.title, id="title"),
            Label("Status"),
            Select(
                _STATUS_OPTIONS,
                value=self._initial.status.value,
                id="status",
            ),
            Horizontal(
                Checkbox("Priority", value=bool(self._initial.priority), id="priority"),
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

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        self._submit()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id in {"due_date"}:
            self._update_due_date_hint()

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
        Binding("o", "open_link", "Open link", show=False),
        Binding("alt+up", "move_up", "Move up", show=False),
        Binding("alt+down", "move_down", "Move down", show=False),
    ]

    def __init__(self, repo: TaskRepository):
        super().__init__(id="tasks")
        self._repo = repo
        self._rows: list[_TaskRow] = []

    def compose(self) -> ComposeResult:
        yield Container(
            Horizontal(
                Label("Tasks"),
                classes="page_header",
            ),
            Static(
                "[dim]n new • s subtask • m notes • e/enter edit • x delete • c status • "
                "p priority • o open link • alt+↑/↓ reorder[/dim]",
                classes="page_help",
            ),
            ListView(id="tasks_list", classes="task_list"),
        )

    def on_mount(self) -> None:
        self._refresh()

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
        old_scroll_y: int | None = None
        if keep_scroll:
            old_scroll_y = getattr(lv, "scroll_y", None)

        roots = list(self._repo.list_tasks())
        roots.sort(key=lambda t: (t.order, t.created_at))

        rows: list[_TaskRow] = []
        for t in roots:
            rows.extend(_flatten_task_tree(t, depth=0, parent_id=None))

        today = today or today_local()
        # Hide DONE tasks from previous days; keep only those completed today.
        # (Non-DONE tasks remain visible regardless of date.)
        filtered_rows: list[_TaskRow] = []
        for row in rows:
            if row.task.status == TaskStatus.DONE:
                completed = row.task.completed_at or row.task.updated_at
                done_day = completed.astimezone().date()
                if done_day < today:
                    continue
            filtered_rows.append(row)

        self._rows = filtered_rows

        lv.clear()

        if not self._rows:
            lv.append(ListItem(Label("(No tasks) — press n to create one")))
            return

        selected_idx = 0
        if keep_id:
            for idx, row in enumerate(self._rows):
                if str(row.task.id) == keep_id:
                    selected_idx = idx
                    break

        for row in self._rows:
            lv.append(self._build_list_item(row))

        lv.index = selected_idx
        if old_scroll_y is not None:
            try:
                lv.scroll_y = old_scroll_y
            except Exception:  # noqa: BLE001
                pass

        if focus:
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

        row_widget = Horizontal(priority, status, title, link_w, due_w, classes="task_list_row")

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
        if t.status == TaskStatus.DONE:
            item.add_class("task_done")
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

            link_text = ""
            if updated.link is not None:
                link_text = updated.link.display_text()
            item.query_one(".task_link", Static).update(link_text)

            if updated.status == TaskStatus.DONE:
                item.add_class("task_done")
            else:
                item.remove_class("task_done")

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
        )
        screen = TaskFormScreen(title="Edit task", initial=initial)

        def _on_dismiss(result: TaskFormResult | None) -> None:
            if result is None:
                return
            try:
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
                self._update_selected_item_in_place(updated)
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
            updated = cycle_task_status(self._repo, task.id)
            self._update_selected_item_in_place(updated)
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

        try:
            if direction == -1:
                move_task_up(self._repo, task.id)
            else:
                move_task_down(self._repo, task.id)
        except ValidationError as e:
            self._notify(f"Error: {e}")
            lv.focus()
            return

        # Update in-memory rows by swapping whole root blocks.
        cur_block = self._rows[cur_start : cur_end + 1]
        neighbor_block = self._rows[neighbor_start : neighbor_end + 1]
        if direction == -1:
            self._rows = (
                self._rows[:neighbor_start]
                + cur_block
                + neighbor_block
                + self._rows[cur_end + 1 :]
            )
        else:
            self._rows = (
                self._rows[:cur_start]
                + neighbor_block
                + cur_block
                + self._rows[neighbor_end + 1 :]
            )

        # Reorder DOM nodes without unmounting (preserves children, focus, scroll).
        items = list(lv.query(ListItem))
        if cur_end >= len(items) or neighbor_end >= len(items):
            self._refresh(keep_id=str(task.id))
            return

        if direction == -1:
            anchor = items[neighbor_start]
            for li in reversed(items[cur_start : cur_end + 1]):
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
