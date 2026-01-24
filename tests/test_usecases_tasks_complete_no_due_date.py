"""Tests for completing recurring tasks without due_date."""

from datetime import datetime, timezone

from logui.domain.entities.task import TaskStatus
from logui.infrastructure.repositories.tasks_repo_json import JsonTaskRepository
from logui.usecases.tasks import CreateTaskInput, create_task, cycle_task_status


def test_completing_recurring_task_without_due_date_auto_assigns_and_clones(tmp_path):
    """When completing a recurring task without due_date, it should auto-assign today and clone."""
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    
    # Create task without due_date but with repetition
    task = create_task(
        repo,
        CreateTaskInput(
            title="Weekly habit",
            status=TaskStatus.TODO,
            priority=False,
            due_date=None,
        ),
    )
    task.repeat = {"freq": "weekly"}
    repo.upsert_task(task)
    
    # Complete it (cycle to DONE)
    now = datetime(2026, 1, 24, 10, 0, 0, tzinfo=timezone.utc)  # Friday
    for _ in range(4):
        updated = cycle_task_status(repo, task.id, now=now)
    
    assert updated.status == TaskStatus.DONE
    # Should have auto-assigned due_date to today
    assert updated.due_date == now.astimezone().date()
    
    # Should have created a new task for next week
    all_tasks = list(repo.list_tasks())
    assert len(all_tasks) == 2
    
    new_task = [t for t in all_tasks if t.id != task.id][0]
    assert new_task.title == "Weekly habit"
    assert new_task.status == TaskStatus.TODO
    # Next Friday (7 days later)
    from datetime import date
    assert new_task.due_date == date(2026, 1, 31)
    assert new_task.repeat == {"freq": "weekly"}


def test_completing_daily_recurring_task_without_due_date(tmp_path):
    """Daily recurring task without due_date gets today and clones for tomorrow."""
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    
    task = create_task(
        repo,
        CreateTaskInput(
            title="Daily exercise",
            status=TaskStatus.TODO,
            priority=False,
            due_date=None,
        ),
    )
    task.repeat = {"freq": "daily"}
    repo.upsert_task(task)
    
    now = datetime(2026, 1, 24, 10, 0, 0, tzinfo=timezone.utc)
    for _ in range(4):
        updated = cycle_task_status(repo, task.id, now=now)
    
    assert updated.status == TaskStatus.DONE
    assert updated.due_date == now.astimezone().date()
    
    all_tasks = list(repo.list_tasks())
    assert len(all_tasks) == 2
    
    new_task = [t for t in all_tasks if t.id != task.id][0]
    from datetime import date
    assert new_task.due_date == date(2026, 1, 25)  # Tomorrow


def test_completing_task_with_due_date_preserves_original_date(tmp_path):
    """Task with due_date should not have it changed when completing."""
    from datetime import date
    
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    
    original_due = date(2026, 1, 20)  # Past date
    task = create_task(
        repo,
        CreateTaskInput(
            title="Late task",
            status=TaskStatus.TODO,
            priority=False,
            due_date=original_due,
        ),
    )
    task.repeat = {"freq": "daily"}
    repo.upsert_task(task)
    
    # Complete it on Jan 24
    now = datetime(2026, 1, 24, 10, 0, 0, tzinfo=timezone.utc)
    for _ in range(4):
        updated = cycle_task_status(repo, task.id, now=now)
    
    assert updated.status == TaskStatus.DONE
    # Should preserve original due_date
    assert updated.due_date == original_due
    
    # New task should be based on original due_date (Jan 21)
    all_tasks = list(repo.list_tasks())
    new_task = [t for t in all_tasks if t.id != task.id][0]
    assert new_task.due_date == date(2026, 1, 21)
