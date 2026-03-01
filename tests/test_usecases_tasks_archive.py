"""Tests for automatic archiving of completed tasks."""

from datetime import datetime, timedelta, timezone

from logui.domain.entities.task import TaskStatus
from logui.infrastructure.persistence import SQLiteDatabase
from logui.infrastructure.repositories.tasks_repo_sqlite import SqliteTaskRepository
from logui.usecases.tasks import CreateTaskInput, archive_completed_tasks, create_task, update_task, UpdateTaskPatch


def test_archive_completed_tasks_over_threshold(tmp_path) -> None:
    """Test that tasks completed over 1 day ago are archived."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    # Create a task completed 2 days ago
    now = datetime.now(timezone.utc)
    two_days_ago = now - timedelta(days=2)
    
    task = create_task(repo, CreateTaskInput(title="Old completed task"))
    update_task(repo, task.id, UpdateTaskPatch(status=TaskStatus.DONE), now=two_days_ago)
    
    # Archive tasks older than 1 day
    archived_count = archive_completed_tasks(repo, days_threshold=1, now=now)
    
    assert archived_count == 1
    
    # Verify task is not in the list anymore (archived tasks are filtered out)
    tasks = repo.list_tasks()
    assert len(tasks) == 0


def test_archive_does_not_affect_recent_completed_tasks(tmp_path) -> None:
    """Test that recently completed tasks are not archived."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    # Create a task completed 12 hours ago
    now = datetime.now(timezone.utc)
    twelve_hours_ago = now - timedelta(hours=12)
    
    task = create_task(repo, CreateTaskInput(title="Recently completed task"))
    update_task(repo, task.id, UpdateTaskPatch(status=TaskStatus.DONE), now=twelve_hours_ago)
    
    # Archive tasks older than 1 day
    archived_count = archive_completed_tasks(repo, days_threshold=1, now=now)
    
    assert archived_count == 0
    
    # Verify task is still in the list
    tasks = repo.list_tasks()
    assert len(tasks) == 1
    assert tasks[0].title == "Recently completed task"


def test_archive_does_not_affect_incomplete_tasks(tmp_path) -> None:
    """Test that incomplete tasks are never archived."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    # Create incomplete tasks
    create_task(repo, CreateTaskInput(title="TODO task", status=TaskStatus.TODO))
    create_task(repo, CreateTaskInput(title="In progress task", status=TaskStatus.IN_PROGRESS))
    
    # Try to archive
    now = datetime.now(timezone.utc)
    archived_count = archive_completed_tasks(repo, days_threshold=1, now=now)
    
    assert archived_count == 0
    
    # Verify tasks are still in the list
    tasks = repo.list_tasks()
    assert len(tasks) == 2


def test_archive_with_subtasks(tmp_path) -> None:
    """Test that subtasks are also archived when completed long ago."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    # Create parent task with subtask, both completed 2 days ago
    now = datetime.now(timezone.utc)
    two_days_ago = now - timedelta(days=2)
    
    parent = create_task(repo, CreateTaskInput(title="Parent task"))
    update_task(repo, parent.id, UpdateTaskPatch(status=TaskStatus.DONE), now=two_days_ago)
    
    # Get updated parent to add subtask
    parent = repo.get_task(parent.id)
    assert parent is not None
    
    from logui.usecases.tasks import create_subtask
    subtask = create_subtask(repo, parent.id, CreateTaskInput(title="Subtask"))
    update_task(repo, subtask.id, UpdateTaskPatch(status=TaskStatus.DONE), now=two_days_ago)
    
    # Archive tasks older than 1 day
    archived_count = archive_completed_tasks(repo, days_threshold=1, now=now)
    
    # Both parent and subtask should be archived
    assert archived_count == 2
    
    # Verify no tasks in list
    tasks = repo.list_tasks()
    assert len(tasks) == 0


def test_archive_mixed_completion_times(tmp_path) -> None:
    """Test archiving with mixed completion times."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    now = datetime.now(timezone.utc)
    
    # Task 1: Completed 3 days ago - should be archived
    three_days_ago = now - timedelta(days=3)
    task1 = create_task(repo, CreateTaskInput(title="Very old task"))
    update_task(repo, task1.id, UpdateTaskPatch(status=TaskStatus.DONE), now=three_days_ago)
    
    # Task 2: Completed 1.5 days ago - should be archived
    one_half_days_ago = now - timedelta(days=1.5)
    task2 = create_task(repo, CreateTaskInput(title="Old task"))
    update_task(repo, task2.id, UpdateTaskPatch(status=TaskStatus.DONE), now=one_half_days_ago)
    
    # Task 3: Completed 12 hours ago - should NOT be archived
    twelve_hours_ago = now - timedelta(hours=12)
    task3 = create_task(repo, CreateTaskInput(title="Recent task"))
    update_task(repo, task3.id, UpdateTaskPatch(status=TaskStatus.DONE), now=twelve_hours_ago)
    
    # Task 4: Not completed - should NOT be archived
    task4 = create_task(repo, CreateTaskInput(title="Incomplete task"))
    
    # Archive tasks older than 1 day
    archived_count = archive_completed_tasks(repo, days_threshold=1, now=now)
    
    assert archived_count == 2
    
    # Verify only recent and incomplete tasks remain
    tasks = repo.list_tasks()
    assert len(tasks) == 2
    titles = {t.title for t in tasks}
    assert titles == {"Recent task", "Incomplete task"}


def test_archive_custom_threshold(tmp_path) -> None:
    """Test archiving with custom threshold."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    now = datetime.now(timezone.utc)
    
    # Task completed 8 days ago
    eight_days_ago = now - timedelta(days=8)
    task = create_task(repo, CreateTaskInput(title="Old task"))
    update_task(repo, task.id, UpdateTaskPatch(status=TaskStatus.DONE), now=eight_days_ago)
    
    # Archive tasks older than 7 days
    archived_count = archive_completed_tasks(repo, days_threshold=7, now=now)
    
    assert archived_count == 1
    tasks = repo.list_tasks()
    assert len(tasks) == 0
    
    # With a 10-day threshold, nothing should be archived
    # Create another task
    task2 = create_task(repo, CreateTaskInput(title="Another old task"))
    update_task(repo, task2.id, UpdateTaskPatch(status=TaskStatus.DONE), now=eight_days_ago)
    
    archived_count = archive_completed_tasks(repo, days_threshold=10, now=now)
    assert archived_count == 0
    tasks = repo.list_tasks()
    assert len(tasks) == 1
