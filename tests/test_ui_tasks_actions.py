from __future__ import annotations

import asyncio
from datetime import date

from textual.app import App, ComposeResult
from textual.widgets import ListItem, ListView
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


def test_task_items_get_status_classes_and_update_on_cycle(tmp_path) -> None:
    from logui.domain.entities.task import Task, TaskStatus
    from logui.infrastructure.persistence.sqlite_database import SQLiteDatabase
    from logui.infrastructure.repositories.tasks_repo_sqlite import SqliteTaskRepository
    from logui.ui.screens.tasks import TasksPane

    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)
    repo.upsert_task(
        Task.create(
            "Active task",
            status=TaskStatus.IN_PROGRESS,
            priority=True,
            due_date=date.today(),
        )
    )
    repo.upsert_task(Task.create("Done task", status=TaskStatus.DONE, order=1.0))

    async def _run() -> None:
        app = TasksTestApp(repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            tasks = app.query_one("#tasks", TasksPane)
            lv = tasks.query_one("#tasks_list", ListView)
            items = list(lv.query(ListItem))

            assert items[0].has_class("task_status_in_progress")
            assert items[0].has_class("task_is_priority")
            assert items[0].has_class("task_due_today_or_past")
            assert not items[0].has_class("task_status_done")
            assert not items[0].has_class("task_done")

            assert items[1].has_class("task_status_done")
            assert items[1].has_class("task_done")
            assert not items[1].has_class("task_is_priority")
            assert not items[1].has_class("task_due_today_or_past")

            tasks.action_toggle_priority()
            await pilot.pause()

            toggled_items = list(lv.query(ListItem))
            assert not toggled_items[0].has_class("task_is_priority")

            lv.index = 0
            tasks.action_cycle_status()
            await pilot.pause()

            updated_items = list(lv.query(ListItem))
            assert updated_items[0].has_class("task_status_postponed")
            assert not updated_items[0].has_class("task_status_in_progress")
            assert not updated_items[0].has_class("task_done")

    asyncio.run(_run())


def test_reorder_tasks_with_sparse_order_numbers_after_delete(tmp_path) -> None:
    from logui.domain.entities.task import Task
    from logui.infrastructure.persistence.sqlite_database import SQLiteDatabase
    from logui.infrastructure.repositories.tasks_repo_sqlite import SqliteTaskRepository
    from logui.ui.screens.tasks import TasksPane

    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    # Simulate natural gaps caused by deleting tasks.
    t1 = Task.create("task 1", order=5.0)
    removed = Task.create("removed", order=9.0)
    t2 = Task.create("task 2", order=14.0)
    t3 = Task.create("task 3", order=20.0)
    repo.upsert_task(t1)
    repo.upsert_task(removed)
    repo.upsert_task(t2)
    repo.upsert_task(t3)
    assert repo.delete_task(removed.id)

    async def _run() -> None:
        app = TasksTestApp(repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            tasks = app.query_one("#tasks", TasksPane)
            lv = tasks.query_one("#tasks_list", ListView)

            items = list(lv.query(ListItem))
            initial_titles = [
                str(item.query_one(".task_title", Static).render()).strip() for item in items
            ]
            assert initial_titles == ["task 1", "task 2", "task 3"]

            # Move middle task up: insert before task 1 using available gap.
            lv.index = 1
            tasks.action_move_up()
            await pilot.pause()

            items = list(lv.query(ListItem))
            after_up_titles = [
                str(item.query_one(".task_title", Static).render()).strip() for item in items
            ]
            assert after_up_titles == ["task 2", "task 1", "task 3"]

            # Move selected task (task 2) down: insert between task 1 and task 3.
            tasks.action_move_down()
            await pilot.pause()

            items = list(lv.query(ListItem))
            after_down_titles = [
                str(item.query_one(".task_title", Static).render()).strip() for item in items
            ]
            assert after_down_titles == ["task 1", "task 2", "task 3"]

            roots = sorted(repo.list_tasks(), key=lambda t: (t.order, t.created_at))
            assert [t.title for t in roots] == ["task 1", "task 2", "task 3"]
            assert [t.order for t in roots] == [5.0, 12.5, 20.0]

    asyncio.run(_run())


def test_reorder_tasks_with_sparse_order_numbers_with_hidden_completed(tmp_path) -> None:
    from datetime import timedelta, timezone

    from logui.domain.entities.task import Task, TaskStatus, utc_now
    from logui.infrastructure.persistence.sqlite_database import SQLiteDatabase
    from logui.infrastructure.repositories.tasks_repo_sqlite import SqliteTaskRepository
    from logui.ui.screens.tasks import TasksPane

    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    # Simulate natural gaps caused by completed tasks hidden from the list.
    t1 = Task.create("task 1", order=5.0)
    hidden_done = Task.create("done hidden", order=9.0, status=TaskStatus.DONE)
    t2 = Task.create("task 2", order=14.0)
    t3 = Task.create("task 3", order=20.0)

    yesterday = utc_now().astimezone(timezone.utc) - timedelta(days=1)
    hidden_done.completed_at = yesterday
    hidden_done.updated_at = yesterday

    repo.upsert_task(t1)
    repo.upsert_task(hidden_done)
    repo.upsert_task(t2)
    repo.upsert_task(t3)

    async def _run() -> None:
        app = TasksTestApp(repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            tasks = app.query_one("#tasks", TasksPane)
            lv = tasks.query_one("#tasks_list", ListView)

            items = list(lv.query(ListItem))
            initial_titles = [
                str(item.query_one(".task_title", Static).render()).strip() for item in items
            ]
            assert initial_titles == ["task 1", "task 2", "task 3"]

            lv.index = 1
            tasks.action_move_up()
            await pilot.pause()

            items = list(lv.query(ListItem))
            after_up_titles = [
                str(item.query_one(".task_title", Static).render()).strip() for item in items
            ]
            assert after_up_titles == ["task 2", "task 1", "task 3"]

            tasks.action_move_down()
            await pilot.pause()

            items = list(lv.query(ListItem))
            after_down_titles = [
                str(item.query_one(".task_title", Static).render()).strip() for item in items
            ]

            assert after_down_titles == ["task 1", "task 2", "task 3"]

    asyncio.run(_run())


def test_move_down_skips_hidden_gap_and_persists_at_end_after_restart(tmp_path) -> None:
    from datetime import timedelta, timezone

    from logui.domain.entities.task import Task, TaskStatus, utc_now
    from logui.infrastructure.persistence.sqlite_database import SQLiteDatabase
    from logui.infrastructure.repositories.tasks_repo_sqlite import SqliteTaskRepository
    from logui.ui.screens.tasks import TasksPane

    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    top = Task.create("top", order=5.0)
    selected = Task.create("selected", order=14.0)
    hidden_done = Task.create("hidden", order=15.0, status=TaskStatus.DONE)
    target = Task.create("target", order=20.0)

    yesterday = utc_now().astimezone(timezone.utc) - timedelta(days=1)
    hidden_done.completed_at = yesterday
    hidden_done.updated_at = yesterday

    repo.upsert_task(top)
    repo.upsert_task(selected)
    repo.upsert_task(hidden_done)
    repo.upsert_task(target)

    async def _run() -> None:
        app = TasksTestApp(repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            tasks = app.query_one("#tasks", TasksPane)
            lv = tasks.query_one("#tasks_list", ListView)

            initial_titles = [
                str(item.query_one(".task_title", Static).render()).strip()
                for item in lv.query(ListItem)
            ]
            assert initial_titles == ["top", "selected", "target"]

            lv.index = 1
            tasks.action_move_down()
            await pilot.pause()

            visible_titles = [
                str(item.query_one(".task_title", Static).render()).strip()
                for item in lv.query(ListItem)
            ]
            assert visible_titles == ["top", "target", "selected"]

            persisted = {t.title: t.order for t in repo.list_tasks()}
            assert persisted["selected"] == 21.0
            assert persisted["target"] == 20.0
            assert persisted["hidden"] == 15.0

        app2 = TasksTestApp(repo)
        async with app2.run_test() as pilot2:
            await pilot2.pause()
            tasks2 = app2.query_one("#tasks", TasksPane)
            lv2 = tasks2.query_one("#tasks_list", ListView)
            restart_titles = [
                str(item.query_one(".task_title", Static).render()).strip()
                for item in lv2.query(ListItem)
            ]
            assert restart_titles == ["top", "target", "selected"]

    asyncio.run(_run())


def test_move_down_between_visible_tasks_uses_fractional_order_after_restart(tmp_path) -> None:
    from datetime import timedelta, timezone

    from logui.domain.entities.task import Task, TaskStatus, utc_now
    from logui.infrastructure.persistence.sqlite_database import SQLiteDatabase
    from logui.infrastructure.repositories.tasks_repo_sqlite import SqliteTaskRepository
    from logui.ui.screens.tasks import TasksPane

    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    top = Task.create("top", order=5.0)
    selected = Task.create("selected", order=14.0)
    hidden_done = Task.create("hidden", order=15.0, status=TaskStatus.DONE)
    target = Task.create("target", order=20.0)
    tail = Task.create("tail", order=21.0)

    yesterday = utc_now().astimezone(timezone.utc) - timedelta(days=1)
    hidden_done.completed_at = yesterday
    hidden_done.updated_at = yesterday

    repo.upsert_task(top)
    repo.upsert_task(selected)
    repo.upsert_task(hidden_done)
    repo.upsert_task(target)
    repo.upsert_task(tail)

    async def _run() -> None:
        app = TasksTestApp(repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            tasks = app.query_one("#tasks", TasksPane)
            lv = tasks.query_one("#tasks_list", ListView)

            lv.index = 1
            tasks.action_move_down()
            await pilot.pause()

            visible_titles = [
                str(item.query_one(".task_title", Static).render()).strip()
                for item in lv.query(ListItem)
            ]
            assert visible_titles == ["top", "target", "selected", "tail"]

            persisted = {t.title: t.order for t in repo.list_tasks()}
            assert persisted["selected"] == 20.5
            assert persisted["target"] == 20.0
            assert persisted["tail"] == 21.0
            assert persisted["hidden"] == 15.0

        app2 = TasksTestApp(repo)
        async with app2.run_test() as pilot2:
            await pilot2.pause()
            tasks2 = app2.query_one("#tasks", TasksPane)
            lv2 = tasks2.query_one("#tasks_list", ListView)
            restart_titles = [
                str(item.query_one(".task_title", Static).render()).strip()
                for item in lv2.query(ListItem)
            ]
            assert restart_titles == ["top", "target", "selected", "tail"]

    asyncio.run(_run())


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
