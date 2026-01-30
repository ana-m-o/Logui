"""Pantalla de Log: historial de eventos y tareas completadas."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import logging

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer
from textual.reactive import reactive
from textual.widgets import Checkbox, Label, ListItem, ListView, Static

from logui.domain.entities.event import Event
from logui.domain.entities.task import Task, TaskStatus
from logui.domain.ports.events import EventRepository
from logui.domain.ports.journal import JournalRepository
from logui.domain.ports.tasks import TaskRepository
from logui.ui.dates import fmt_day_compact_friendly, fmt_day_full_friendly
from logui.ui.parsing import today_local

_log = logging.getLogger(__name__)


def _escape_rich(text: str) -> str:
    # Textual uses Rich markup by default in Static; escape brackets to avoid
    # interpreting user content as markup.
    return (text or "").replace("[", r"\[").replace("]", r"\]")


def _collect_all_completed_tasks(tasks: list[Task]) -> list[Task]:
    """Collect all completed tasks including subtasks recursively.
    
    Returns a flat list of all completed tasks (DONE status) from the entire tree,
    including both parent tasks and their completed subtasks.
    """
    completed = []
    
    def _traverse(task: Task) -> None:
        if task.status == TaskStatus.DONE:
            completed.append(task)
        # Recursively check subtasks
        for subtask in task.subtasks:
            _traverse(subtask)
    
    for task in tasks:
        _traverse(task)
    
    return completed


class LogPane(Container):
    """Panel de Log con historial de eventos y tareas completadas."""

    show_journal = reactive(False)

    def __init__(self, events_repo: EventRepository, tasks_repo: TaskRepository, journal_repo: JournalRepository):
        super().__init__(id="log")
        self._events_repo = events_repo
        self._tasks_repo = tasks_repo
        self._journal_repo = journal_repo
        self._last_rendered_groups: list[str] | None = None

    def compose(self) -> ComposeResult:
        """Componer widgets del log."""
        yield Container(
            Horizontal(
                Label("Log"),
                classes="page_header",
            ),
            Horizontal(
                Checkbox("Show journal entries", id="log_show_journal"),
                classes="log_toolbar",
            ),
            ListView(id="log_list"),
        )

    def on_mount(self) -> None:
        """Cargar log al montar."""
        # Load saved show_journal preference
        try:
            from logui.domain.ports.config import ConfigRepository
            config_repo = getattr(self.app, "_config_repo", None)
            if config_repo and isinstance(config_repo, ConfigRepository):
                config = config_repo.load()
                self.show_journal = config.ui.show_journal_in_log
                # Update checkbox to match saved state
                try:
                    checkbox = self.query_one("#log_show_journal", Checkbox)
                    checkbox.value = self.show_journal
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass
        self._load_log()
        try:
            log_list = self.query_one("#log_list", ListView)
            log_list.can_focus = True
            log_list.focus()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.query_one("#log_list", ListView).focus()
        except Exception:  # noqa: BLE001
            pass

    def refresh_log(self) -> None:
        """Public refresh hook for the app-level polling loop."""
        self._load_log()

    def on_day_rollover(self, *, today: date) -> None:  # noqa: ARG002
        self._load_log()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle checkbox change."""
        if event.checkbox.id == "log_show_journal":
            self.show_journal = event.value
            # Save preference
            try:
                from logui.domain.ports.config import ConfigRepository
                from logui.usecases.config import set_show_journal_in_log
                config_repo = getattr(self.app, "_config_repo", None)
                if config_repo and isinstance(config_repo, ConfigRepository):
                    set_show_journal_in_log(repo=config_repo, enabled=event.value)
            except Exception as e:  # noqa: BLE001
                _log.warning("Failed saving show_journal preference: %s", e)
            self._load_log()

    def _load_log(self) -> None:
        """Cargar y mostrar el log agrupado por fecha."""
        log_list = self.query_one("#log_list", ListView)
        had_focus = log_list.has_focus
        old_index = log_list.index or 0
        old_scroll_y = getattr(log_list, "scroll_y", None)

        today = today_local()
        
        # Check if auto-hide is enabled to determine if we show today's items in log
        auto_hide_enabled = False
        try:
            from logui.domain.ports.config import ConfigRepository
            config_repo = getattr(self.app, "_config_repo", None)
            if config_repo and isinstance(config_repo, ConfigRepository):
                config = config_repo.load()
                auto_hide_enabled = config.ui.auto_hide_completed
        except Exception:  # noqa: BLE001
            pass

        # Obtener eventos ya terminados (incluyendo hoy solo si auto_hide está activado)
        all_events = list(self._events_repo.list_events())
        past_events: list[Event] = []
        for e in all_events:
            end_day = e.date.fromordinal(e.date.toordinal() + int(e.end_day_offset or 0))
            if auto_hide_enabled:
                # Show today's ended events in log when auto_hide is enabled
                if end_day <= today:
                    past_events.append(e)
            else:
                # Only show past events (not today) when auto_hide is disabled
                if end_day < today:
                    past_events.append(e)

        # Obtener tareas completadas (incluyendo hoy solo si auto_hide está activado)
        all_tasks = list(self._tasks_repo.list_tasks())
        # Use the helper to collect ALL completed tasks including subtasks
        all_completed = _collect_all_completed_tasks(all_tasks)
        if auto_hide_enabled:
            # Show today's completed tasks in log when auto_hide is enabled
            completed_tasks = [
                t
                for t in all_completed
                if (t.completed_at or t.updated_at).astimezone().date() <= today
            ]
        else:
            # Only show past completed tasks (not today) when auto_hide is disabled
            completed_tasks = [
                t
                for t in all_completed
                if (t.completed_at or t.updated_at).astimezone().date() < today
            ]

        # Agrupar por fecha
        entries_by_date: dict[date, list] = defaultdict(list)

        for event in past_events:
            entries_by_date[event.date].append(("event", event))

        for task in completed_tasks:
            completion_date = (task.completed_at or task.updated_at).astimezone().date()
            entries_by_date[completion_date].append(("task", task))

        # Añadir entradas del journal si la opción está habilitada
        if self.show_journal:
            try:
                journal_days = self._journal_repo.list_entry_days()
                for day in journal_days:
                    # Solo mostrar días que ya están en el log o son del pasado
                    if day < today or day in entries_by_date:
                        entry_text = self._journal_repo.get_entry(day)
                        if entry_text and entry_text.strip():
                            entries_by_date[day].append(("journal", entry_text))
            except Exception as e:  # noqa: BLE001
                _log.warning("Failed loading journal entries: %s", e)

        # Build render snapshot (to avoid flicker if nothing changes)
        rendered_groups: list[str] = []

        # Sort dates in descending order (most recent first)
        sorted_dates = sorted(entries_by_date.keys(), reverse=True)
        if not sorted_dates:
            rendered_groups = ["[dim]No past events or completed tasks[/dim]"]
        else:
            for day in sorted_dates:
                date_label = fmt_day_full_friendly(day)

                entries = entries_by_date[day]
                sorted_entries = sorted(entries, key=lambda x: self._get_entry_sort_key(x))

                lines = [f"[bold]{date_label}[/bold]"]
                for entry_type, entry in sorted_entries:
                    if entry_type == "event":
                        lines.append(self._format_event_entry(entry))
                    elif entry_type == "task":
                        lines.append(self._format_task_entry(entry))
                    elif entry_type == "journal":
                        lines.append(self._format_journal_entry(entry))

                rendered_groups.append("\n".join(lines))

        if self._last_rendered_groups == rendered_groups:
            return

        self._last_rendered_groups = list(rendered_groups)

        # Render
        log_list.clear()
        if not sorted_dates:
            log_list.append(
                ListItem(Static(rendered_groups[0]), classes="log_empty")
            )
        else:
            for group_text in rendered_groups:
                log_list.append(
                    ListItem(
                        Static(group_text),
                        classes="log_day_group",
                    )
                )

        # Restore selection/scroll (best effort)
        try:
            if log_list.children:
                log_list.index = max(0, min(old_index, len(log_list.children) - 1))
            if old_scroll_y is not None:
                log_list.scroll_y = old_scroll_y
        except Exception as e:  # noqa: BLE001
            _log.debug("Failed restoring log selection/scroll: %s", e)
        if had_focus:
            try:
                log_list.focus()
            except Exception:  # noqa: BLE001
                pass

    def _get_entry_sort_key(self, entry: tuple[str, Event | Task | str]) -> tuple:
        """Get sort key for an entry."""
        entry_type, item = entry

        if entry_type == "event":
            # Sort events by start_time (or at the end if no time)
            if item.start_time:
                return (0, item.start_time)
            else:
                return (1, datetime.min.time())
        elif entry_type == "task":
            # Sort tasks by update time
            return (0, item.updated_at.time())
        else:  # journal - always at the end of the day
            return (2, datetime.max.time())

    def _format_event_entry(self, event: Event) -> str:
        """Format event entry with indentation."""
        today = today_local()
        start_day = event.date
        end_day = start_day.fromordinal(start_day.toordinal() + int(event.end_day_offset or 0))
        
        is_multi_day = event.end_day_offset and event.end_day_offset > 0

        # Only show date for multi-day events (single-day events already have date in header)
        day_part = ""
        if is_multi_day:
            day_part = f"{fmt_day_compact_friendly(start_day, today=today)}–{fmt_day_compact_friendly(end_day, today=today)}"

        # Format time/duration
        time_part = "All day"
        if event.start_time is not None:
            start_s = event.start_time.strftime("%H:%M")
            end_s = event.end_time.strftime("%H:%M") if event.end_time else "??"
            time_part = f"{start_s}–{end_s}"

        # Build the title line
        if day_part:
            # Multi-day event: show date range and time
            title_line = f"  [dim]{day_part} {time_part}[/dim]  {_escape_rich(event.title)}"
        else:
            # Single-day event: only show time
            title_line = f"  [dim]{time_part}[/dim]  {_escape_rich(event.title)}"

        # Agregar notas si existen
        notes_text = ""
        if event.notes:
            notes_text = "\n".join(
                f"    [dim italic]- {_escape_rich(n.text)}[/]" for n in event.notes
            )
        if notes_text:
            # Indent notes too
            return f"{title_line}\n{notes_text}"
        else:
            return title_line

    def _format_task_entry(self, task: Task) -> str:
        """Format completed task entry with indentation."""
        # Format: ✓ Task title
        completed = task.completed_at or task.updated_at
        completion_time = completed.time().strftime("%H:%M")
        # Note: we escape only the opening bracket so Rich doesn't interpret
        # "[X]" as markup.
        suffix_parts: list[str] = []
        if task.link is not None:
            link_text = (task.link.display_text() or "").strip()
            if link_text:
                suffix_parts.append(_escape_rich(link_text))
        if task.due_date is not None:
            suffix_parts.append(f"({fmt_day_full_friendly(task.due_date)})")

        suffix = ""
        if suffix_parts:
            suffix = "  " + "  ".join(suffix_parts)

        title_line = (
            f"  \\[X] [dim]{completion_time}[/dim] {_escape_rich(task.title)}{suffix}"
        )

        # Agregar notas si existen
        notes_text = ""
        if task.notes:
            notes_text = "\n".join(
                f"    [dim italic]- {_escape_rich(n.text)}[/]" for n in task.notes
            )

        # Agregar subtareas si existen
        subtasks_text = ""
        if task.subtasks:
            subtasks_lines = []
            for st in task.subtasks:
                status_icon = "✓" if st.status == TaskStatus.DONE else "○"
                subtasks_lines.append(f"    {status_icon} {_escape_rich(st.title)}")
            subtasks_text = "\n".join(subtasks_lines)

        # Combinar todo
        parts = [title_line]
        if notes_text:
            parts.append(notes_text)
        if subtasks_text:
            parts.append(subtasks_text)

        return "\n".join(parts)

    def _format_journal_entry(self, text: str) -> str:
        """Format journal entry with indentation."""
        # Show first line or truncated preview
        lines = text.split("\n")
        preview = lines[0] if lines else ""
        if len(preview) > 80:
            preview = preview[:77] + "..."
        
        return f"  [dim italic]📓 {_escape_rich(preview)}[/dim italic]"
