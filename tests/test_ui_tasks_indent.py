"""Tests for UI task indent/unindent actions."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Input

from logui.domain.entities.task import Task
from logui.infrastructure.persistence.sqlite_database import SQLiteDatabase
from logui.infrastructure.repositories.tasks_repo_sqlite import SqliteTaskRepository
from logui.ui.screens.tasks import TaskFormScreen, TasksPane
from logui.usecases.tasks import CreateTaskInput, create_task


class TasksIndentTestApp(App[None]):
    def __init__(self, repo, **kwargs):
        super().__init__(**kwargs)
        self.repo = repo
        self.notifications: list[str] = []

    def notify(self, message: str, *args, **kwargs) -> None:  # type: ignore[override]
        self.notifications.append(str(message))

    def compose(self) -> ComposeResult:
        yield TasksPane(self.repo)


def test_ui_task_indent_action(tmp_path) -> None:
    """Test indent action in UI."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    # Create two tasks
    task1 = create_task(repo, CreateTaskInput(title="Task 1"))
    task2 = create_task(repo, CreateTaskInput(title="Task 2"))

    async def _run() -> None:
        app = TasksIndentTestApp(repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            tasks = app.query_one("#tasks", TasksPane)
            lv = tasks.query_one("#tasks_list")

            # Select second task (Task 2)
            lv.index = 1
            await pilot.pause()

            # Press 'i' to indent
            await pilot.press("i")
            await pilot.pause()

            # Verify notification
            assert any("converted to subtask" in msg.lower() for msg in app.notifications)

            # Verify structure: Task 2 should now be subtask of Task 1
            roots = list(repo.list_tasks())
            assert len(roots) == 1
            assert roots[0].id == task1.id
            assert len(roots[0].subtasks) == 1
            assert roots[0].subtasks[0].id == task2.id

    import asyncio

    asyncio.run(_run())


def test_ui_task_unindent_action(tmp_path) -> None:
    """Test unindent action in UI."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    # Create parent with subtask
    task1 = create_task(repo, CreateTaskInput(title="Task 1"))
    task1_obj = repo.get_task(task1.id)
    assert task1_obj is not None

    subtask = Task.create("Subtask", order=0)
    task1_obj.add_subtask(subtask)
    repo.upsert_task(task1_obj)

    async def _run() -> None:
        app = TasksIndentTestApp(repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            tasks = app.query_one("#tasks", TasksPane)
            lv = tasks.query_one("#tasks_list")

            # Select subtask (second row)
            lv.index = 1
            await pilot.pause()

            # Press 'u' to unindent
            await pilot.press("u")
            await pilot.pause()

            # Verify notification
            assert any("converted to task" in msg.lower() for msg in app.notifications)

            # Verify structure: Subtask should now be a root task
            roots = list(repo.list_tasks())
            assert len(roots) == 2
            root_titles = {r.title for r in roots}
            assert root_titles == {"Task 1", "Subtask"}

    import asyncio

    asyncio.run(_run())


def test_ui_cannot_indent_first_task(tmp_path) -> None:
    """Test that we cannot indent the first task in the list."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    create_task(repo, CreateTaskInput(title="Task 1"))

    async def _run() -> None:
        app = TasksIndentTestApp(repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            tasks = app.query_one("#tasks", TasksPane)
            lv = tasks.query_one("#tasks_list")

            # Select first task
            lv.index = 0
            await pilot.pause()

            # Try to indent
            await pilot.press("i")
            await pilot.pause()

            # Verify error notification
            assert any("already at top" in msg.lower() for msg in app.notifications)

            # Verify structure unchanged
            roots = list(repo.list_tasks())
            assert len(roots) == 1

    import asyncio

    asyncio.run(_run())


def test_ui_cannot_indent_subtask(tmp_path) -> None:
    """Test that we cannot indent a subtask (only 1 level allowed)."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    # Create parent with subtask
    task1 = create_task(repo, CreateTaskInput(title="Task 1"))
    task1_obj = repo.get_task(task1.id)
    assert task1_obj is not None

    subtask = Task.create("Subtask", order=0)
    task1_obj.add_subtask(subtask)
    repo.upsert_task(task1_obj)

    async def _run() -> None:
        app = TasksIndentTestApp(repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            tasks = app.query_one("#tasks", TasksPane)
            lv = tasks.query_one("#tasks_list")

            # Select subtask (second row)
            lv.index = 1
            await pilot.pause()

            # Try to indent
            await pilot.press("i")
            await pilot.pause()

            # Verify error notification
            assert any("already a subtask" in msg.lower() for msg in app.notifications)

    import asyncio

    asyncio.run(_run())


def test_ui_cannot_unindent_root_task(tmp_path) -> None:
    """Test that we cannot unindent a root task."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    create_task(repo, CreateTaskInput(title="Task 1"))

    async def _run() -> None:
        app = TasksIndentTestApp(repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            tasks = app.query_one("#tasks", TasksPane)
            lv = tasks.query_one("#tasks_list")

            # Select first task
            lv.index = 0
            await pilot.pause()

            # Try to unindent
            await pilot.press("u")
            await pilot.pause()

            # Verify error notification
            assert any("already a root task" in msg.lower() for msg in app.notifications)

    import asyncio

    asyncio.run(_run())


def test_ui_indent_when_above_is_subtask(tmp_path) -> None:
    """Test indenting when the task above is a subtask (should find parent)."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    # Create structure: Task1 with SubA, then Task2
    task1 = create_task(repo, CreateTaskInput(title="Task1"))
    task1_obj = repo.get_task(task1.id)
    assert task1_obj is not None

    sub_a = Task.create("SubA", order=0)
    task1_obj.add_subtask(sub_a)
    repo.upsert_task(task1_obj)

    task2 = create_task(repo, CreateTaskInput(title="Task2"))

    async def _run() -> None:
        app = TasksIndentTestApp(repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            tasks = app.query_one("#tasks", TasksPane)
            lv = tasks.query_one("#tasks_list")

            # The list should be: Task1, SubA, Task2
            # Select Task2 (third row, index 2)
            lv.index = 2
            await pilot.pause()

            # Press 'i' to indent - should make Task2 a subtask of Task1 (not SubA)
            await pilot.press("i")
            await pilot.pause()

            # Verify structure: Task2 should be subtask of Task1
            roots = list(repo.list_tasks())
            assert len(roots) == 1
            assert roots[0].title == "Task1"
            assert len(roots[0].subtasks) == 2
            subtask_titles = {st.title for st in roots[0].subtasks}
            assert subtask_titles == {"SubA", "Task2"}

    import asyncio

    asyncio.run(_run())
