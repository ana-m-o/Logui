"""Test task recurrence completion and cloning logic."""
from datetime import date

from logui.domain.entities.task import TaskStatus
from logui.infrastructure.repositories.tasks_repo_json import JsonTaskRepository
from logui.usecases.tasks import create_task, cycle_task_status, CreateTaskInput


def test_completing_recurring_task_clones_for_next_occurrence(tmp_path):
    """When a recurring task is marked DONE, it should clone itself for the next occurrence."""
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    
    # Create daily recurring task with due_date
    task = create_task(
        repo,
        CreateTaskInput(
            title="Daily exercise",
            status=TaskStatus.TODO,
            priority=False,
            due_date=date(2026, 1, 24),
        ),
    )
    task.repeat = {"freq": "daily"}
    repo.upsert_task(task)

    # Cycle status until DONE (todo → in_progress → postponed → in_review → done)
    updated = task
    for _ in range(4):
        updated = cycle_task_status(repo, task.id)

    assert updated.status == TaskStatus.DONE
    assert updated.due_date == date(2026, 1, 24)
    
    # Should have created a new task for next day
    all_tasks = list(repo.list_tasks())
    assert len(all_tasks) == 2
    
    new_task = [t for t in all_tasks if t.id != task.id][0]
    assert new_task.title == "Daily exercise"
    assert new_task.status == TaskStatus.TODO
    assert new_task.due_date == date(2026, 1, 25)
    assert new_task.repeat == {"freq": "daily"}


def test_completing_weekly_recurring_task_clones_for_next_week(tmp_path):
    """Weekly recurring task clones for next week."""
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    
    task = create_task(
        repo,
        CreateTaskInput(
            title="Weekly review",
            status=TaskStatus.TODO,
            priority=False,
            due_date=date(2026, 1, 24),  # Friday
        ),
    )
    task.repeat = {"freq": "weekly"}
    repo.upsert_task(task)
    
    # Cycle status until DONE
    for _ in range(4):
        cycle_task_status(repo, task.id)
    
    all_tasks = list(repo.list_tasks())
    assert len(all_tasks) == 2
    
    new_task = [t for t in all_tasks if t.id != task.id][0]
    assert new_task.due_date == date(2026, 1, 31)  # Next Friday


def test_completing_recurring_task_with_subtasks_clones_subtasks(tmp_path):
    """Recurring task with subtasks clones all subtasks."""
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    
    task = create_task(
        repo,
        CreateTaskInput(
            title="Weekly meeting",
            status=TaskStatus.TODO,
            priority=False,
            due_date=date(2026, 1, 24),
        ),
    )
    task.repeat = {"freq": "weekly"}
    repo.upsert_task(task)

    # Add subtasks using the usecase
    from logui.usecases.tasks import create_subtask
    subtask1 = create_subtask(
        repo, task.id,
        CreateTaskInput(title="Prepare agenda", status=TaskStatus.TODO, priority=False, due_date=None)
    )
    subtask2 = create_subtask(
        repo, task.id,
        CreateTaskInput(title="Send notes", status=TaskStatus.TODO, priority=False, due_date=None)
    )
    
    # Cycle status until DONE
    for _ in range(4):
        cycle_task_status(repo, task.id)
    
    all_tasks = list(repo.list_tasks())
    assert len(all_tasks) == 2
    
    new_task = [t for t in all_tasks if t.id != task.id][0]
    assert len(new_task.subtasks) == 2
    assert new_task.subtasks[0].title == "Prepare agenda"
    assert new_task.subtasks[0].status == TaskStatus.TODO
    assert new_task.subtasks[1].title == "Send notes"
    assert new_task.subtasks[1].status == TaskStatus.TODO


def test_completing_task_without_recurrence_does_not_clone(tmp_path):
    """Non-recurring tasks don't clone when marked DONE."""
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    
    task = create_task(
        repo,
        CreateTaskInput(
            title="One-time task",
            status=TaskStatus.TODO,
            priority=False,
            due_date=date(2026, 1, 24),
        ),
    )
    
    # Cycle status until DONE
    for _ in range(4):
        cycle_task_status(repo, task.id)
    
    all_tasks = list(repo.list_tasks())
    assert len(all_tasks) == 1
    assert all_tasks[0].status == TaskStatus.DONE


def test_completing_recurring_task_without_due_date_auto_assigns_and_clones(tmp_path):
    """Recurring tasks without due_date auto-assign today and clone."""
    from datetime import datetime, timezone
    
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    
    task = create_task(
        repo,
        CreateTaskInput(
            title="No due date task",
            status=TaskStatus.TODO,
            priority=False,
            due_date=None,
        ),
    )
    task.repeat = {"freq": "daily"}
    repo.upsert_task(task)
    
    # Cycle status until DONE
    now = datetime(2026, 1, 24, 10, 0, 0, tzinfo=timezone.utc)
    for _ in range(4):
        cycle_task_status(repo, task.id, now=now)
    
    all_tasks = list(repo.list_tasks())
    # Should have cloned (original DONE + new TODO)
    assert len(all_tasks) == 2
    
    completed = [t for t in all_tasks if t.status == TaskStatus.DONE][0]
    assert completed.due_date == now.astimezone().date()
    
    new_task = [t for t in all_tasks if t.status == TaskStatus.TODO][0]
    assert new_task.due_date == date(2026, 1, 25)


def test_completing_recurring_task_respects_until_date(tmp_path):
    """Recurring tasks with 'until' don't clone after that date."""
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    
    task = create_task(
        repo,
        CreateTaskInput(
            title="Limited series",
            status=TaskStatus.TODO,
            priority=False,
            due_date=date(2026, 1, 24),
        ),
    )
    task.repeat = {"freq": "daily", "until": "2026-01-24"}
    repo.upsert_task(task)
    
    # Cycle status until DONE
    for _ in range(4):
        cycle_task_status(repo, task.id)
    
    # Should not clone because 'until' date is reached
    all_tasks = list(repo.list_tasks())
    assert len(all_tasks) == 1
    assert all_tasks[0].status == TaskStatus.DONE
