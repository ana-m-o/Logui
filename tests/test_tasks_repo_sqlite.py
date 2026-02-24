"""Tests for SqliteTaskRepository."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from logui.domain.entities.task import Task, TaskLink, TaskStatus
from logui.infrastructure.persistence import SQLiteDatabase
from logui.infrastructure.repositories.tasks_repo_sqlite import SqliteTaskRepository


def test_sqlite_task_repo_empty(tmp_path: Path) -> None:
    """Test repository with no tasks."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)
    
    assert repo.list_tasks() == []


def test_sqlite_task_repo_upsert_and_get(tmp_path: Path) -> None:
    """Test upserting and retrieving a task."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)
    
    # Create task
    task = Task.create(
        "Write documentation",
        order=0,
        status=TaskStatus.TODO,
        priority=True,
        due_date=date(2026, 3, 20),
    )
    
    # Upsert
    repo.upsert_task(task)
    
    # Get and verify
    loaded = repo.get_task(task.id)
    assert loaded is not None
    assert loaded.id == task.id
    assert loaded.title == "Write documentation"
    assert loaded.status == TaskStatus.TODO
    assert loaded.priority is True
    assert loaded.due_date == date(2026, 3, 20)


def test_sqlite_task_repo_upsert_updates(tmp_path: Path) -> None:
    """Test that upsert updates existing task."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)
    
    # Create and upsert task
    task = Task.create("Original", order=0)
    repo.upsert_task(task)
    
    # Update and upsert again
    task.title = "Updated"
    task.status = TaskStatus.IN_PROGRESS
    task.touch()
    repo.upsert_task(task)
    
    # Verify update
    loaded = repo.get_task(task.id)
    assert loaded is not None
    assert loaded.title == "Updated"
    assert loaded.status == TaskStatus.IN_PROGRESS
    
    # Should only have one task
    tasks = repo.list_tasks()
    assert len(tasks) == 1


def test_sqlite_task_repo_delete(tmp_path: Path) -> None:
    """Test deleting a task."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)
    
    # Create and upsert task
    task = Task.create("Test Task", order=0)
    repo.upsert_task(task)
    
    # Delete
    deleted = repo.delete_task(task.id)
    assert deleted is True
    
    # Verify deletion
    assert repo.get_task(task.id) is None
    assert repo.list_tasks() == []
    
    # Delete again should return False
    deleted_again = repo.delete_task(task.id)
    assert deleted_again is False


def test_sqlite_task_repo_task_with_notes(tmp_path: Path) -> None:
    """Test task with multiple notes."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)
    
    # Create task and add notes
    task = Task.create("Task with notes", order=0)
    task.add_note("First note")
    task.add_note("Second note")
    
    # Upsert
    repo.upsert_task(task)
    
    # Load and verify notes
    loaded = repo.get_task(task.id)
    assert loaded is not None
    assert len(loaded.notes) == 2
    assert loaded.notes[0].text == "First note"
    assert loaded.notes[1].text == "Second note"


def test_sqlite_task_repo_task_with_link(tmp_path: Path) -> None:
    """Test task with link."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)
    
    # Create task with link
    link = TaskLink.create("https://example.com/doc", text="Documentation")
    task = Task.create("Read docs", order=0, link=link)
    
    repo.upsert_task(task)
    
    # Load and verify link
    loaded = repo.get_task(task.id)
    assert loaded is not None
    assert loaded.link is not None
    assert loaded.link.url == "https://example.com/doc"
    assert loaded.link.text == "Documentation"


def test_sqlite_task_repo_task_with_subtasks(tmp_path: Path) -> None:
    """Test task with subtasks."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)
    
    # Create parent task with subtasks
    parent = Task.create("Parent Task", order=0)
    subtask1 = Task.create("Subtask 1", order=0)
    subtask2 = Task.create("Subtask 2", order=1)
    
    parent.add_subtask(subtask1)
    parent.add_subtask(subtask2)
    
    # Upsert
    repo.upsert_task(parent)
    
    # Load and verify subtasks
    loaded = repo.get_task(parent.id)
    assert loaded is not None
    assert len(loaded.subtasks) == 2
    assert loaded.subtasks[0].title == "Subtask 1"
    assert loaded.subtasks[1].title == "Subtask 2"
    
    # Subtasks should also be retrievable individually
    loaded_sub1 = repo.get_task(subtask1.id)
    assert loaded_sub1 is not None
    assert loaded_sub1.title == "Subtask 1"


def test_sqlite_task_repo_delete_task_cascades_subtasks(tmp_path: Path) -> None:
    """Test that deleting parent task CASCADE deletes subtasks."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)
    
    # Create parent with subtask
    parent = Task.create("Parent", order=0)
    subtask = Task.create("Subtask", order=0)
    parent.add_subtask(subtask)
    
    repo.upsert_task(parent)
    
    # Verify subtask exists in database
    conn = db.get_connection()
    cursor = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE parent_task_id = ?",
        (str(parent.id),)
    )
    assert cursor.fetchone()[0] == 1
    
    # Delete parent
    repo.delete_task(parent.id)
    
    # Verify subtask was CASCADE deleted
    cursor = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE parent_task_id = ?",
        (str(parent.id),)
    )
    assert cursor.fetchone()[0] == 0
    
    # Subtask should not be retrievable
    assert repo.get_task(subtask.id) is None


def test_sqlite_task_repo_nested_subtasks(tmp_path: Path) -> None:
    """Test tasks with nested subtasks (3 levels)."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)
    
    # Create 3-level hierarchy
    root = Task.create("Root", order=0)
    child = Task.create("Child", order=0)
    grandchild = Task.create("Grandchild", order=0)
    
    child.add_subtask(grandchild)
    root.add_subtask(child)
    
    # Upsert
    repo.upsert_task(root)
    
    # Load and verify hierarchy
    loaded = repo.get_task(root.id)
    assert loaded is not None
    assert len(loaded.subtasks) == 1
    assert loaded.subtasks[0].title == "Child"
    assert len(loaded.subtasks[0].subtasks) == 1
    assert loaded.subtasks[0].subtasks[0].title == "Grandchild"


def test_sqlite_task_repo_list_tasks_only_returns_roots(tmp_path: Path) -> None:
    """Test that list_tasks only returns root tasks, not subtasks."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)
    
    # Create parent with subtask
    parent = Task.create("Parent", order=0)
    subtask = Task.create("Subtask", order=0)
    parent.add_subtask(subtask)
    
    repo.upsert_task(parent)
    
    # list_tasks should only return root task
    tasks = repo.list_tasks()
    assert len(tasks) == 1
    assert tasks[0].id == parent.id


def test_sqlite_task_repo_list_tasks_sorted_by_order(tmp_path: Path) -> None:
    """Test that list_tasks returns tasks sorted by order_num."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)
    
    # Create tasks in random order
    task3 = Task.create("Task 3", order=2)
    task1 = Task.create("Task 1", order=0)
    task2 = Task.create("Task 2", order=1)
    
    for task in [task3, task1, task2]:
        repo.upsert_task(task)
    
    # List should be sorted by order
    tasks = repo.list_tasks()
    assert len(tasks) == 3
    assert tasks[0].title == "Task 1"
    assert tasks[1].title == "Task 2"
    assert tasks[2].title == "Task 3"


def test_sqlite_task_repo_task_with_repeat(tmp_path: Path) -> None:
    """Test task with recurrence configuration."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)
    
    # Create recurring task
    task = Task.create(
        "Weekly review",
        order=0,
        due_date=date(2026, 3, 3),
        repeat={
            "freq": "weekly",
            "interval": 1,
        },
    )
    
    repo.upsert_task(task)
    
    # Load and verify repeat config
    loaded = repo.get_task(task.id)
    assert loaded is not None
    assert loaded.repeat is not None
    assert loaded.repeat["freq"] == "weekly"
    assert loaded.repeat["interval"] == 1


def test_sqlite_task_repo_task_statuses(tmp_path: Path) -> None:
    """Test tasks with different statuses."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)
    
    statuses = [
        TaskStatus.TODO,
        TaskStatus.IN_PROGRESS,
        TaskStatus.POSTPONED,
        TaskStatus.IN_REVIEW,
        TaskStatus.DONE,
    ]
    
    tasks = []
    for i, status in enumerate(statuses):
        task = Task.create(f"Task {status.value}", order=i, status=status)
        tasks.append(task)
        repo.upsert_task(task)
    
    # Verify all statuses
    for task in tasks:
        loaded = repo.get_task(task.id)
        assert loaded is not None
        assert loaded.status == task.status


def test_sqlite_task_repo_task_notes_replaced_on_update(tmp_path: Path) -> None:
    """Test that notes are replaced when task is updated."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)
    
    # Create task with one note
    task = Task.create("Test", order=0)
    task.add_note("First note")
    repo.upsert_task(task)
    
    # Update task with different notes
    task.notes.clear()
    task.add_note("Second note")
    task.add_note("Third note")
    repo.upsert_task(task)
    
    # Verify notes were replaced
    loaded = repo.get_task(task.id)
    assert loaded is not None
    assert len(loaded.notes) == 2
    assert loaded.notes[0].text == "Second note"
    assert loaded.notes[1].text == "Third note"


def test_sqlite_task_repo_multiple_root_tasks(tmp_path: Path) -> None:
    """Test repository with multiple root tasks."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)
    
    # Create multiple root tasks
    tasks = [
        Task.create("Task 1", order=0),
        Task.create("Task 2", order=1),
        Task.create("Task 3", order=2),
    ]
    
    for task in tasks:
        repo.upsert_task(task)
    
    # Verify all tasks
    loaded_tasks = repo.list_tasks()
    assert len(loaded_tasks) == 3
    
    # Verify each task can be retrieved individually
    for task in tasks:
        loaded = repo.get_task(task.id)
        assert loaded is not None
        assert loaded.id == task.id


def test_sqlite_task_repo_get_nonexistent(tmp_path: Path) -> None:
    """Test getting a non-existent task."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)
    
    from uuid import uuid4
    fake_id = uuid4()
    
    result = repo.get_task(fake_id)
    assert result is None


def test_sqlite_task_repo_task_completed(tmp_path: Path) -> None:
    """Test task with completed status has completed_at timestamp."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)
    
    # Create completed task
    task = Task.create("Done task", order=0, status=TaskStatus.DONE)
    assert task.completed_at is not None
    
    repo.upsert_task(task)
    
    # Verify completed_at is stored
    loaded = repo.get_task(task.id)
    assert loaded is not None
    assert loaded.status == TaskStatus.DONE
    assert loaded.completed_at is not None
