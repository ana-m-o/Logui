"""Test for list_tasks optimization with include_old_completed parameter."""

from datetime import datetime, timedelta, timezone

from logui.domain.entities.task import Task, TaskStatus
from logui.infrastructure.persistence.sqlite_database import SQLiteDatabase
from logui.infrastructure.repositories.tasks_repo_sqlite import SqliteTaskRepository


def test_list_tasks_filters_old_completed_when_requested(tmp_path):
    """Test that list_tasks with include_old_completed=False filters DONE tasks from previous days."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)

    # Create a task completed yesterday
    old_task = Task.create(
        "Completed yesterday",
        status=TaskStatus.DONE,
        now=yesterday,
    )
    repo.upsert_task(old_task)

    # Create a task completed today
    recent_task = Task.create(
        "Completed today",
        status=TaskStatus.DONE,
        now=now,
    )
    repo.upsert_task(recent_task)

    # Create an incomplete task
    todo_task = Task.create(
        "Still todo",
        status=TaskStatus.TODO,
    )
    repo.upsert_task(todo_task)

    # With include_old_completed=True (default), should get all 3 tasks
    all_tasks = repo.list_tasks(include_old_completed=True)
    assert len(all_tasks) == 3
    titles = {t.title for t in all_tasks}
    assert titles == {"Completed yesterday", "Completed today", "Still todo"}

    # With include_old_completed=False, should only get today's completed + incomplete
    active_tasks = repo.list_tasks(include_old_completed=False)
    assert len(active_tasks) == 2
    active_titles = {t.title for t in active_tasks}
    assert active_titles == {"Completed today", "Still todo"}


def test_list_tasks_default_behavior_unchanged(tmp_path):
    """Test that list_tasks() without arguments still returns all non-archived tasks."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    now = datetime.now(timezone.utc)
    two_days_ago = now - timedelta(days=2)

    # Create various tasks
    old_task = Task.create("Old done", status=TaskStatus.DONE, now=two_days_ago)
    repo.upsert_task(old_task)

    recent_task = Task.create("Recent done", status=TaskStatus.DONE, now=now)
    repo.upsert_task(recent_task)

    todo_task = Task.create("Todo", status=TaskStatus.TODO)
    repo.upsert_task(todo_task)

    # Default behavior should return all tasks
    all_tasks = repo.list_tasks()
    assert len(all_tasks) == 3


def test_list_tasks_optimization_with_subtasks(tmp_path):
    """Test that optimization correctly handles parent tasks with subtasks."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)

    # Create parent task completed yesterday
    from logui.usecases.tasks import CreateTaskInput, create_task, create_subtask, update_task, UpdateTaskPatch
    
    parent = create_task(repo, CreateTaskInput(title="Parent task"))
    
    # Add subtask
    subtask = create_subtask(repo, parent.id, CreateTaskInput(title="Subtask"))
    
    # Complete both tasks yesterday
    update_task(repo, parent.id, UpdateTaskPatch(status=TaskStatus.DONE), now=yesterday)
    update_task(repo, subtask.id, UpdateTaskPatch(status=TaskStatus.DONE), now=yesterday)

    # With optimization, parent task should be filtered out (including its subtasks)
    active_tasks = repo.list_tasks(include_old_completed=False)
    assert len(active_tasks) == 0

    # Without optimization, should see parent with subtask
    all_tasks = repo.list_tasks(include_old_completed=True)
    assert len(all_tasks) == 1
    assert all_tasks[0].title == "Parent task"
    assert len(all_tasks[0].subtasks) == 1
    assert all_tasks[0].subtasks[0].title == "Subtask"
