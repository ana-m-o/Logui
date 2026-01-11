from __future__ import annotations

import asyncio
from datetime import date

from textual.app import App, ComposeResult
from textual.widgets import Input, Label, ListItem, ListView, Static


class NotesTestApp(App[None]):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.notifications: list[str] = []

    def notify(self, message: str, *args, **kwargs) -> None:  # type: ignore[override]
        # Capture notifications rather than rendering toasts.
        self.notifications.append(str(message))

    def compose(self) -> ComposeResult:
        yield Static("root", id="root")


def _label_text(label: Label) -> str:
    renderable = getattr(label, "renderable", "")
    plain = getattr(renderable, "plain", None)
    if isinstance(plain, str):
        return plain
    return str(renderable)


def _list_view_texts(lv: ListView) -> list[str]:
    # ListView items may not be discoverable via query() reliably in tests.
    items = [w for w in lv.children if isinstance(w, ListItem)]
    texts: list[str] = []
    for item in items:
        try:
            lbl = item.query_one(Label)
        except Exception:  # noqa: BLE001
            continue
        texts.append(_label_text(lbl))
    return texts


def test_event_notes_screen_new_edit_delete(tmp_path) -> None:
    from logui.domain.entities.event import Event
    from logui.infrastructure.repositories.events_repo_json import JsonEventRepository
    from logui.ui.screens.event_notes import EventNotesScreen, NoteEditorScreen
    from logui.ui.screens.modals import ConfirmScreen

    repo = JsonEventRepository(tmp_path / "events.json")
    event = Event.create("Event", day=date.today())
    repo.upsert_event(event)

    async def _run() -> None:
        app = NotesTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            app.push_screen(EventNotesScreen(repo, event))
            await pilot.pause()
            await pilot.pause()

            notes = app.screen
            assert isinstance(notes, EventNotesScreen)

            # Ensure initial state is rendered.
            notes._refresh()  # noqa: SLF001
            await pilot.pause()

            # Basic sanity: widget exists.
            notes.query_one("#notes_list", ListView)

            # New note
            notes.action_new()
            await pilot.pause()
            assert isinstance(app.screen, NoteEditorScreen)

            editor = app.screen
            editor.query_one("#note_text", Input).value = "hello"
            editor.action_submit()
            await pilot.pause()

            assert isinstance(app.screen, EventNotesScreen)
            ev = repo.get_event(event.id)
            assert ev is not None
            assert [n.text for n in ev.notes] == ["hello"]
            assert "Note added" in app.notifications

            # Edit note
            notes = app.screen
            notes.action_edit()
            await pilot.pause()
            assert isinstance(app.screen, NoteEditorScreen)

            editor = app.screen
            editor.query_one("#note_text", Input).value = "updated"
            editor.action_submit()
            await pilot.pause()

            assert isinstance(app.screen, EventNotesScreen)
            ev = repo.get_event(event.id)
            assert ev is not None
            assert [n.text for n in ev.notes] == ["updated"]
            assert "Note updated" in app.notifications

            # Delete note
            notes = app.screen
            notes.action_delete()
            await pilot.pause()
            assert isinstance(app.screen, ConfirmScreen)

            app.screen.action_yes()
            await pilot.pause()

            assert isinstance(app.screen, EventNotesScreen)
            ev = repo.get_event(event.id)
            assert ev is not None
            assert ev.notes == []
            assert "Note deleted" in app.notifications

    asyncio.run(_run())


def test_task_notes_screen_new_edit_delete(tmp_path) -> None:
    from logui.domain.entities.task import Task
    from logui.infrastructure.repositories.tasks_repo_json import JsonTaskRepository
    from logui.ui.screens.modals import ConfirmScreen
    from logui.ui.screens.task_notes import NoteEditorScreen, TaskNotesScreen

    repo = JsonTaskRepository(tmp_path / "tasks.json")
    task = Task.create("Task", order=0)
    repo.upsert_task(task)

    async def _run() -> None:
        app = NotesTestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            app.push_screen(TaskNotesScreen(repo, task.id))
            await pilot.pause()
            await pilot.pause()

            notes = app.screen
            assert isinstance(notes, TaskNotesScreen)

            # Ensure initial state is rendered.
            notes._refresh()  # noqa: SLF001
            await pilot.pause()

            # Basic sanity: widget exists.
            notes.query_one("#notes_list", ListView)

            # New note
            notes.action_new()
            await pilot.pause()
            assert isinstance(app.screen, NoteEditorScreen)

            editor = app.screen
            editor.query_one("#note_text", Input).value = "hello"
            editor.action_submit()
            await pilot.pause()

            assert isinstance(app.screen, TaskNotesScreen)
            t = repo.get_task(task.id)
            assert t is not None
            assert [n.text for n in t.notes] == ["hello"]
            assert "Note added" in app.notifications

            # Edit note
            notes = app.screen
            notes.action_edit()
            await pilot.pause()
            assert isinstance(app.screen, NoteEditorScreen)

            editor = app.screen
            editor.query_one("#note_text", Input).value = "updated"
            editor.action_submit()
            await pilot.pause()

            assert isinstance(app.screen, TaskNotesScreen)
            t = repo.get_task(task.id)
            assert t is not None
            assert [n.text for n in t.notes] == ["updated"]
            assert "Note updated" in app.notifications

            # Delete note
            notes = app.screen
            notes.action_delete()
            await pilot.pause()
            assert isinstance(app.screen, ConfirmScreen)

            app.screen.action_yes()
            await pilot.pause()

            assert isinstance(app.screen, TaskNotesScreen)
            t = repo.get_task(task.id)
            assert t is not None
            assert t.notes == []
            assert "Note deleted" in app.notifications

    asyncio.run(_run())
