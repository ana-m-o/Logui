from __future__ import annotations

import asyncio
from datetime import date

from textual.app import App, ComposeResult
from textual.widgets import Checkbox, Input, Static


class TasksTestApp(App[None]):
    def __init__(self, repo, **kwargs):
        super().__init__(**kwargs)
        self.repo = repo
        self.notifications: list[str] = []

    def notify(self, message: str, *args, **kwargs) -> None:  # type: ignore[override]
        self.notifications.append(str(message))

    def compose(self) -> ComposeResult:
        from logui.ui.screens.tasks import TasksPane

        yield TasksPane(self.repo)


def test_tasks_crud_and_actions(tmp_path) -> None:
    from logui.infrastructure.persistence.sqlite_database import SQLiteDatabase
    from logui.infrastructure.repositories.tasks_repo_sqlite import SqliteTaskRepository
    from logui.ui.screens.modals import ConfirmScreen
    from logui.ui.screens.task_notes import TaskNotesScreen
    from logui.ui.screens.tasks import TaskFormScreen, TasksPane

    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    async def _run() -> None:
        app = TasksTestApp(repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            tasks = app.query_one("#tasks", TasksPane)

            # Create a new task via modal submit.
            tasks.action_new()
            await pilot.pause()
            assert isinstance(app.screen, TaskFormScreen)

            form = app.screen
            form.query_one("#title", Input).value = "T1"
            form.query_one("#due_date", Input).value = date.today().isoformat()
            form.query_one("#priority", Checkbox).value = True
            form.query_one("#link_url", Input).value = "https://example.com"
            form.query_one("#link_text", Input).value = "Example"
            form.action_submit()
            await pilot.pause()

            created = repo.list_tasks()
            assert len(created) == 1
            t1 = created[0]
            assert t1.title == "T1"
            assert t1.due_date == date.today()
            assert t1.priority is True
            assert t1.link is not None
            assert t1.link.url == "https://example.com"
            assert t1.link.text == "Example"
            assert "Task created" in app.notifications

            # Edit task via modal submit.
            tasks.action_edit()
            await pilot.pause()
            assert isinstance(app.screen, TaskFormScreen)

            form = app.screen
            form.query_one("#title", Input).value = "T1-updated"
            form.query_one("#priority", Checkbox).value = False
            form.action_submit()
            await pilot.pause()

            t1b = repo.get_task(t1.id)
            assert t1b is not None
            assert t1b.title == "T1-updated"
            assert t1b.priority is False
            assert "Task updated" in app.notifications

            # Toggle priority and cycle status actions (no modal).
            tasks.action_toggle_priority()
            await pilot.pause()
            t1c = repo.get_task(t1.id)
            assert t1c is not None
            assert t1c.priority is True

            prev_status = t1c.status
            tasks.action_cycle_status()
            await pilot.pause()
            t1d = repo.get_task(t1.id)
            assert t1d is not None
            assert t1d.status != prev_status
            expected_label = t1d.status.value.replace("_", " ").title()
            assert any(
                m == f"Task status: {expected_label}" or m.endswith(f": {expected_label}")
                for m in app.notifications
            )

            # Create a second root task so move_up has something to do.
            tasks.action_new()
            await pilot.pause()
            assert isinstance(app.screen, TaskFormScreen)

            form = app.screen
            form.query_one("#title", Input).value = "T2"
            form.action_submit()
            await pilot.pause()

            roots = sorted(repo.list_tasks(), key=lambda t: (t.order, t.created_at))
            assert [t.title for t in roots] == ["T1-updated", "T2"]

            # Open notes modal from tasks pane and close.
            tasks.action_notes()
            await pilot.pause()
            assert isinstance(app.screen, TaskNotesScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, TaskNotesScreen)

            # Select second root task and move it up.
            lv = tasks.query_one("#tasks_list")
            lv.index = 1
            tasks.action_move_up()
            await pilot.pause()

            roots2 = sorted(repo.list_tasks(), key=lambda t: (t.order, t.created_at))
            assert [t.title for t in roots2] == ["T2", "T1-updated"]

            # Select T1 and create a subtask under it.
            lv.index = 1
            await pilot.pause()

            # Create a subtask under the selected task.
            tasks.action_new_subtask()
            await pilot.pause()
            assert isinstance(app.screen, TaskFormScreen)

            form = app.screen
            form.query_one("#title", Input).value = "S1"
            form.query_one("#link_url", Input).value = "https://example.com/sub"
            form.query_one("#link_text", Input).value = "SubExample"
            form.action_submit()
            await pilot.pause()

            roots = repo.list_tasks()
            assert len(roots) == 2
            t1_root = next(t for t in roots if t.title == "T1-updated")
            assert [st.title for st in t1_root.subtasks] == ["S1"]
            assert t1_root.subtasks[0].link is not None
            assert t1_root.subtasks[0].link.url == "https://example.com/sub"
            assert t1_root.subtasks[0].link.text == "SubExample"
            assert "Subtask created" in app.notifications

            # Attempt to create a subtask with link_text but no link_url: should fail validation.
            tasks.action_new_subtask()
            await pilot.pause()
            assert isinstance(app.screen, TaskFormScreen)

            form = app.screen
            form.query_one("#title", Input).value = "S2"
            form.query_one("#link_text", Input).value = "NoUrl"
            form.action_submit()
            await pilot.pause()

            # Still on the modal and error shown.
            assert isinstance(app.screen, TaskFormScreen)
            err = app.screen.query_one("#task_form_error", Static).render()
            assert "Link text requires a URL" in str(err)

            # Cancel out of the modal.
            await pilot.press("escape")
            await pilot.pause()

            roots_after = repo.list_tasks()
            t1_root_after = next(t for t in roots_after if t.title == "T1-updated")
            assert [st.title for st in t1_root_after.subtasks] == ["S1"]

            # Delete currently selected task via confirm.
            tasks.action_delete()
            await pilot.pause()
            assert isinstance(app.screen, ConfirmScreen)

            app.screen.action_yes()
            await pilot.pause()

            remaining = [
                t.title for t in sorted(repo.list_tasks(), key=lambda t: (t.order, t.created_at))
            ]
            assert remaining == ["T2", "T1-updated"]
            assert "Task deleted" in app.notifications

            # Delete the remaining first root task (T2) as well.
            tasks.action_delete()
            await pilot.pause()
            assert isinstance(app.screen, ConfirmScreen)

            app.screen.action_yes()
            await pilot.pause()

            remaining2 = [
                t.title for t in sorted(repo.list_tasks(), key=lambda t: (t.order, t.created_at))
            ]
            assert remaining2 == ["T1-updated"]

    asyncio.run(_run())
