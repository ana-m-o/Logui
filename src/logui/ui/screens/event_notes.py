from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView, Static

from logui.domain.entities.event import Event
from logui.domain.ports.events import EventRepository
from logui.ui.screens.modals import ConfirmScreen
from logui.usecases.events import (
    add_event_note,
    delete_event_note,
    move_event_note_down,
    move_event_note_up,
    update_event_note,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class NoteEditorResult:
    text: str


class NoteEditorScreen(ModalScreen[NoteEditorResult | None]):
    BINDINGS = [
        Binding("enter", "submit", "Save", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, *, title: str, initial_text: str):
        super().__init__()
        self._title = title
        self._initial_text = initial_text
        self.add_class("modal")

    def compose(self) -> ComposeResult:
        yield Container(
            Label(self._title, id="note_editor_title", classes="modal_title"),
            Static(
                "[dim]enter save • esc cancel[/dim]",
                id="note_editor_help",
                classes="modal_help",
            ),
            Input(value=self._initial_text, id="note_text"),
            Static("", id="note_editor_error", classes="modal_error"),
            id="note_editor",
            classes="modal_box modal_w80",
        )

    def on_mount(self) -> None:
        self.query_one("#note_text", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        self._submit()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def _submit(self) -> None:
        error = self.query_one("#note_editor_error", Static)
        error.update("")
        text = self.query_one("#note_text", Input).value

        errors: list[str] = []
        if not (text or "").strip():
            errors.append("Note cannot be empty. Type some text and press Enter")

        if errors:
            error.update("[red]" + "\n".join(f"• {m}" for m in errors) + "[/red]")
            return

        self.dismiss(NoteEditorResult(text=text))


class EventNotesScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("n", "new", "New", show=False),
        Binding("e", "edit", "Edit", show=False),
        Binding("enter", "edit", "Edit", show=False),
        Binding("x", "delete", "Delete", show=False),
        Binding("alt+up", "move_up", "Move up", show=False),
        Binding("alt+down", "move_down", "Move down", show=False),
        Binding("escape", "back", "Back", show=False),
    ]

    def __init__(
        self,
        repo: EventRepository,
        event: Event,
        *,
        on_changed: Callable[[Event], None] | None = None,
    ):
        super().__init__()
        self._repo = repo
        self._event_id = event.id
        self._on_changed = on_changed
        self.add_class("modal")

    def _notify_changed(self) -> None:
        if not callable(self._on_changed):
            return
        ev = self._get_event()
        if ev is None:
            return
        self._on_changed(ev)

    def compose(self) -> ComposeResult:
        yield Container(
            Label("Notes", id="notes_title", classes="modal_title"),
            Static(
                "[dim]n new • enter/e edit • x delete • alt+↑/↓ reorder • esc back[/dim]",
                id="notes_help",
                classes="modal_help",
            ),
            ListView(id="notes_list", classes="modal_list"),
            id="notes",
            classes="modal_box modal_w80 modal_h1fr",
        )

    def on_mount(self) -> None:
        self._refresh()

    def action_back(self) -> None:
        self.dismiss(None)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle ListView selection (enter key)."""
        self.action_edit()

    def _notify(self, message: str) -> None:
        notify = getattr(self.app, "notify", None)
        if callable(notify):
            notify(message)

    def _get_event(self) -> Event | None:
        return self._repo.get_event(self._event_id)

    def _refresh(self) -> None:
        ev = self._get_event()
        lv = self.query_one("#notes_list", ListView)
        # Preserve current selection
        current_index = lv.index if lv.index is not None else 0
        lv.clear()

        if ev is None:
            lv.append(ListItem(Static("(Event not found)")))
            return

        if not ev.notes:
            lv.append(ListItem(Static("(No notes) — press n to create")))
            return

        for note in ev.notes:
            lv.append(ListItem(Static(note.text, markup=False)))

        if len(ev.notes) > 0:
            # Restore index, but ensure it's within bounds
            lv.index = min(current_index, len(ev.notes) - 1)
            # Use call_later to ensure the ListView is fully updated before focusing
            self.call_later(lv.focus)

    def _selected_note_id(self) -> UUID | None:
        ev = self._get_event()
        if ev is None or not ev.notes:
            return None
        lv = self.query_one("#notes_list", ListView)
        idx = lv.index or 0
        if idx < 0 or idx >= len(ev.notes):
            return None
        return ev.notes[idx].id

    def _update_selected_item(self, new_text: str) -> None:
        """Update only the selected item without refreshing the whole list."""
        lv = self.query_one("#notes_list", ListView)
        idx = lv.index or 0
        if idx < 0 or idx >= len(lv):
            return
        # Replace the item at the current index
        lv.pop(idx)  # Remove old item
        new_item = ListItem(Static(new_text, markup=False))
        lv.mount(new_item, before=idx)
        lv.index = idx

    def _remove_selected_item(self) -> None:
        """Remove only the selected item without refreshing the whole list."""
        lv = self.query_one("#notes_list", ListView)
        idx = lv.index or 0
        if idx < 0 or idx >= len(lv):
            return

        # If this is the last note, do a full refresh to show the "No notes" message
        if len(lv) == 1:
            self._refresh()
        else:
            # Otherwise, just remove the item
            lv.pop(idx)
            lv.index = min(idx, len(lv) - 1)

    def action_new(self) -> None:
        screen = NoteEditorScreen(title="New note", initial_text="")

        def _on_dismiss(result: NoteEditorResult | None) -> None:
            if result is None:
                return
            try:
                add_event_note(self._repo, self._event_id, result.text, now=utc_now())
                self._refresh()
                self._notify("Note added")
                self._notify_changed()
            except Exception as e:  # noqa: BLE001
                self._notify(f"Error: {e}")

        self.app.push_screen(screen, callback=_on_dismiss)

    def action_edit(self) -> None:
        ev = self._get_event()
        note_id = self._selected_note_id()
        if ev is None or note_id is None:
            return

        note = next((n for n in ev.notes if n.id == note_id), None)
        if note is None:
            return

        screen = NoteEditorScreen(title="Edit note", initial_text=note.text)
        selected_note_id = note_id

        def _on_dismiss(result: NoteEditorResult | None) -> None:
            if result is None:
                return
            try:
                update_event_note(
                    self._repo,
                    self._event_id,
                    selected_note_id,
                    result.text,
                    now=utc_now(),
                )
                self._update_selected_item(result.text)
                self._notify("Note updated")
                self._notify_changed()
            except Exception as e:  # noqa: BLE001
                self._notify(f"Error: {e}")

        self.app.push_screen(screen, callback=_on_dismiss)

    def action_delete(self) -> None:
        ev = self._get_event()
        note_id = self._selected_note_id()
        if ev is None or note_id is None:
            return

        note = next((n for n in ev.notes if n.id == note_id), None)
        if note is None:
            return

        selected_note_id = note_id

        def _on_confirm(ok: bool) -> None:
            if not ok:
                return
            try:
                delete_event_note(self._repo, self._event_id, selected_note_id, now=utc_now())
                self._remove_selected_item()
                self._notify("Note deleted")
                self._notify_changed()
            except Exception as e:  # noqa: BLE001
                self._notify(f"Error: {e}")

        self.app.push_screen(ConfirmScreen("Delete note?"), callback=_on_confirm)

    def action_move_up(self) -> None:
        note_id = self._selected_note_id()
        if note_id is None:
            return

        ev = self._get_event()
        if ev is None:
            return

        lv = self.query_one("#notes_list", ListView)
        idx = lv.index or 0

        # Can't move first item up
        if idx == 0:
            return

        try:
            move_event_note_up(self._repo, self._event_id, note_id, now=utc_now())

            # Move the DOM node without rebuilding the entire list
            items = list(lv.query(ListItem))
            if idx < len(items) and idx - 1 >= 0:
                lv.move_child(items[idx], before=items[idx - 1])
                lv.index = idx - 1

            self._notify_changed()
        except Exception as e:  # noqa: BLE001
            self._notify(f"Error: {e}")

    def action_move_down(self) -> None:
        note_id = self._selected_note_id()
        if note_id is None:
            return

        ev = self._get_event()
        if ev is None:
            return

        lv = self.query_one("#notes_list", ListView)
        idx = lv.index or 0

        # Can't move last item down
        if idx >= len(ev.notes) - 1:
            return

        try:
            move_event_note_down(self._repo, self._event_id, note_id, now=utc_now())

            # Move the DOM node without rebuilding the entire list
            items = list(lv.query(ListItem))
            if idx < len(items) and idx + 1 < len(items):
                lv.move_child(items[idx], after=items[idx + 1])
                lv.index = idx + 1

            self._notify_changed()
        except Exception as e:  # noqa: BLE001
            self._notify(f"Error: {e}")
