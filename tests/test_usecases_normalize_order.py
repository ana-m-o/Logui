"""Tests for normalize_task_order use case."""

from datetime import date, datetime, timezone

from logui.domain.entities.task import Task, TaskStatus
from logui.infrastructure.persistence.sqlite_database import SQLiteDatabase
from logui.infrastructure.repositories.tasks_repo_sqlite import SqliteTaskRepository
from logui.usecases.tasks import create_task, CreateTaskInput, normalize_task_order


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def test_normalize_task_order_basic(tmp_path):
    """Test that normalize_task_order resets order values to sequential integers."""
    with SQLiteDatabase(tmp_path / "test.db") as db:
        db.init_schema()
        repo = SqliteTaskRepository(db)
        now = _utc_now()

        # Create tasks with fractional order values
        t1 = create_task(repo, CreateTaskInput(title="Task 1"), now=now)
        t1.order = 0.5
        repo.upsert_task(t1)

        t2 = create_task(repo, CreateTaskInput(title="Task 2"), now=now)
        t2.order = 1.25
        repo.upsert_task(t2)

        t3 = create_task(repo, CreateTaskInput(title="Task 3"), now=now)
        t3.order = 1.75
        repo.upsert_task(t3)

        # Normalize
        normalize_task_order(repo, now=now)

        # Verify order values are now clean integers
        tasks = sorted(list(repo.list_tasks()), key=lambda t: (t.order, t.created_at))
        assert len(tasks) == 3
        assert tasks[0].title == "Task 1"
        assert tasks[0].order == 0.0
        assert tasks[1].title == "Task 2"
        assert tasks[1].order == 1.0
        assert tasks[2].title == "Task 3"
        assert tasks[2].order == 2.0


def test_normalize_task_order_with_subtasks(tmp_path):
    """Test that normalize_task_order also normalizes subtask orders."""
    with SQLiteDatabase(tmp_path / "test.db") as db:
        db.init_schema()
        repo = SqliteTaskRepository(db)
        now = _utc_now()

        # Create parent task with subtasks
        parent = Task.create(title="Parent", now=now, order=5.5)
        
        sub1 = Task.create(title="Sub 1", now=now, order=0.3)
        sub2 = Task.create(title="Sub 2", now=now, order=1.7)
        sub3 = Task.create(title="Sub 3", now=now, order=2.2)
        
        parent.add_subtask(sub1, now=now)
        parent.add_subtask(sub2, now=now)
        parent.add_subtask(sub3, now=now)
        
        repo.upsert_task(parent)

        # Normalize
        normalize_task_order(repo, now=now)

        # Verify parent and subtasks are normalized
        tasks = list(repo.list_tasks())
        assert len(tasks) == 1
        normalized_parent = tasks[0]
        assert normalized_parent.order == 0.0
        
        sorted_subtasks = sorted(normalized_parent.subtasks, key=lambda t: (t.order, t.created_at))
        assert len(sorted_subtasks) == 3
        assert sorted_subtasks[0].title == "Sub 1"
        assert sorted_subtasks[0].order == 0.0
        assert sorted_subtasks[1].title == "Sub 2"
        assert sorted_subtasks[1].order == 1.0
        assert sorted_subtasks[2].title == "Sub 3"
        assert sorted_subtasks[2].order == 2.0


def test_normalize_task_order_preserves_relative_order(tmp_path):
    """Test that normalize_task_order preserves relative ordering."""
    with SQLiteDatabase(tmp_path / "test.db") as db:
        db.init_schema()
        repo = SqliteTaskRepository(db)
        now = _utc_now()

        # Create tasks in specific order with complex fractional values
        t1 = create_task(repo, CreateTaskInput(title="First"), now=now)
        t1.order = 10.5
        repo.upsert_task(t1)

        t2 = create_task(repo, CreateTaskInput(title="Second"), now=now)
        t2.order = 20.25
        repo.upsert_task(t2)

        t3 = create_task(repo, CreateTaskInput(title="Third"), now=now)
        t3.order = 15.75
        repo.upsert_task(t3)

        # Get original order
        tasks_before = sorted(list(repo.list_tasks()), key=lambda t: (t.order, t.created_at))
        titles_before = [t.title for t in tasks_before]

        # Normalize
        normalize_task_order(repo, now=now)

        # Verify relative order is preserved
        tasks_after = sorted(list(repo.list_tasks()), key=lambda t: (t.order, t.created_at))
        titles_after = [t.title for t in tasks_after]
        
        assert titles_before == titles_after
        assert titles_after == ["First", "Third", "Second"]
        
        # Verify clean sequential values
        assert tasks_after[0].order == 0.0
        assert tasks_after[1].order == 1.0
        assert tasks_after[2].order == 2.0


def test_normalize_task_order_empty_repo(tmp_path):
    """Test that normalize_task_order handles empty repository gracefully."""
    with SQLiteDatabase(tmp_path / "test.db") as db:
        db.init_schema()
        repo = SqliteTaskRepository(db)
        now = _utc_now()

        # Should not raise any errors
        normalize_task_order(repo, now=now)
        
        tasks = list(repo.list_tasks())
        assert len(tasks) == 0


def test_normalize_task_order_updates_timestamps(tmp_path):
    """Test that normalize_task_order updates the updated_at timestamp."""
    with SQLiteDatabase(tmp_path / "test.db") as db:
        db.init_schema()
        repo = SqliteTaskRepository(db)
        
        early = datetime(2020, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        later = datetime(2020, 1, 2, 12, 0, 0, tzinfo=timezone.utc)

        # Create task with early timestamp
        t1 = create_task(repo, CreateTaskInput(title="Task 1"), now=early)
        t1.order = 0.5
        repo.upsert_task(t1)

        # Normalize with later timestamp
        normalize_task_order(repo, now=later)

        # Verify updated_at was updated
        tasks = list(repo.list_tasks())
        assert len(tasks) == 1
        assert tasks[0].updated_at == later
