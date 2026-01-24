"""Tests for task recurrence when no due_date is set."""

from datetime import datetime, timezone

from logui.domain.entities.task import TaskStatus
from logui.infrastructure.repositories.tasks_repo_json import JsonTaskRepository
from logui.usecases.tasks import CreateTaskInput, create_task, cycle_task_repeat


def test_cycle_repeat_assigns_due_date_when_activating_repetition(tmp_path):
    """When activating repetition on a task without due_date, it should auto-assign today."""
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    
    # Create task without due_date
    task = create_task(
        repo,
        CreateTaskInput(
            title="Task without due date",
            status=TaskStatus.TODO,
            priority=False,
            due_date=None,
        ),
    )
    
    assert task.due_date is None
    assert task.repeat is None or task.repeat == {"freq": "none"}
    
    # Activate repetition
    now = datetime(2026, 1, 24, 10, 0, 0, tzinfo=timezone.utc)
    updated = cycle_task_repeat(repo, task.id, now=now)
    
    # Should have due_date assigned to today
    expected_date = now.astimezone().date()
    assert updated.due_date == expected_date
    assert updated.repeat == {"freq": "daily"}


def test_cycle_repeat_preserves_existing_due_date(tmp_path):
    """When cycling repetition on a task with due_date, it should preserve the date."""
    from datetime import date
    
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    
    due = date(2026, 2, 15)
    task = create_task(
        repo,
        CreateTaskInput(
            title="Task with due date",
            status=TaskStatus.TODO,
            priority=False,
            due_date=due,
        ),
    )
    
    assert task.due_date == due
    
    # Activate repetition
    updated = cycle_task_repeat(repo, task.id)
    
    # Should preserve existing due_date
    assert updated.due_date == due
    assert updated.repeat == {"freq": "daily"}


def test_cycle_repeat_no_due_date_assigned_when_deactivating(tmp_path):
    """When deactivating repetition (any freq → none), don't modify due_date."""
    from datetime import date
    
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    
    # Create task without due_date
    task = create_task(
        repo,
        CreateTaskInput(
            title="Task",
            status=TaskStatus.TODO,
            priority=False,
            due_date=None,
        ),
    )
    
    # Activate repetition (will assign due_date)
    now = datetime(2026, 1, 24, 10, 0, 0, tzinfo=timezone.utc)
    updated1 = cycle_task_repeat(repo, task.id, now=now)
    assert updated1.due_date is not None
    assert updated1.repeat == {"freq": "daily"}
    
    # Continue cycling: daily → weekly
    updated2 = cycle_task_repeat(repo, updated1.id, now=now)
    assert updated2.due_date == updated1.due_date
    assert updated2.repeat == {"freq": "weekly"}
    
    # Continue cycling: weekly → monthly
    updated3 = cycle_task_repeat(repo, updated2.id, now=now)
    assert updated3.due_date == updated1.due_date
    assert updated3.repeat == {"freq": "monthly"}
    
    # Continue cycling: monthly → none (deactivate)
    updated4 = cycle_task_repeat(repo, updated3.id, now=now)
    # Should keep the due_date that was assigned
    assert updated4.due_date == updated1.due_date
    assert updated4.repeat == {"freq": "none"}


def test_cycle_repeat_only_assigns_on_first_activation(tmp_path):
    """Due date should only be auto-assigned when first activating repetition."""
    from datetime import date
    
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    
    # Create task without due_date
    task = create_task(
        repo,
        CreateTaskInput(
            title="Task",
            status=TaskStatus.TODO,
            priority=False,
            due_date=None,
        ),
    )
    
    # First activation: none → daily (should assign due_date)
    now1 = datetime(2026, 1, 24, 10, 0, 0, tzinfo=timezone.utc)
    updated1 = cycle_task_repeat(repo, task.id, now=now1)
    first_due_date = updated1.due_date
    assert first_due_date is not None
    
    # Cycle to weekly
    updated2 = cycle_task_repeat(repo, updated1.id, now=now1)
    assert updated2.due_date == first_due_date
    
    # Deactivate (monthly → none)
    updated3 = cycle_task_repeat(repo, updated2.id, now=now1)
    updated4 = cycle_task_repeat(repo, updated3.id, now=now1)
    assert updated4.repeat == {"freq": "none"}
    assert updated4.due_date == first_due_date
    
    # Now manually remove the due_date
    from logui.usecases.tasks import UpdateTaskPatch, update_task
    cleared = update_task(repo, updated4.id, UpdateTaskPatch(due_date=None))
    assert cleared.due_date is None
    
    # Activate again on a different day
    now2 = datetime(2026, 1, 30, 10, 0, 0, tzinfo=timezone.utc)
    reactivated = cycle_task_repeat(repo, cleared.id, now=now2)
    
    # Should assign new due_date (today on activation day)
    expected_new_date = now2.astimezone().date()
    assert reactivated.due_date == expected_new_date
    assert reactivated.due_date != first_due_date
