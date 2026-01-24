"""Test recurring tasks."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from logui.domain.entities.task import Task, TaskStatus
from logui.infrastructure.repositories.tasks_repo_json import JsonTaskRepository
from logui.usecases import cycle_task_repeat


def test_task_with_repeat_field_persists(tmp_path: Path) -> None:
    """Task repeat field is saved and loaded correctly."""
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    
    task = Task.create(
        "Daily review",
        order=0,
        status=TaskStatus.TODO,
        due_date=date(2026, 1, 15),
        repeat={"freq": "daily", "interval": 1},
    )
    repo.upsert_task(task)
    
    # Reload and verify
    loaded = repo.get_task(task.id)
    assert loaded is not None
    assert loaded.repeat == {"freq": "daily", "interval": 1}


def test_task_occurs_on_checks_due_date_with_repeat(tmp_path: Path) -> None:
    """Task.occurs_on() uses due_date as base for recurrence."""
    task = Task.create(
        "Weekly backup",
        order=0,
        status=TaskStatus.TODO,
        due_date=date(2026, 1, 15),  # Thursday
        repeat={"freq": "weekly", "interval": 1},
    )
    
    # Occurs on the due date
    assert task.occurs_on(date(2026, 1, 15)) is True
    
    # Occurs one week later
    assert task.occurs_on(date(2026, 1, 22)) is True
    
    # Does NOT occur on other days
    assert task.occurs_on(date(2026, 1, 16)) is False
    assert task.occurs_on(date(2026, 1, 20)) is False


def test_task_occurs_on_returns_false_without_due_date(tmp_path: Path) -> None:
    """Tasks without due_date cannot determine occurrences."""
    task = Task.create(
        "Someday task",
        order=0,
        status=TaskStatus.TODO,
        due_date=None,
        repeat={"freq": "daily", "interval": 1},
    )
    
    # No due date = no occurrence dates
    assert task.occurs_on(date(2026, 1, 15)) is False
    assert task.occurs_on(date(2026, 1, 20)) is False


def test_task_daily_recurrence(tmp_path: Path) -> None:
    """Daily tasks occur every day from due_date."""
    task = Task.create(
        "Daily standup",
        order=0,
        status=TaskStatus.TODO,
        due_date=date(2026, 1, 15),
        repeat={"freq": "daily", "interval": 1},
    )
    
    assert task.occurs_on(date(2026, 1, 15)) is True
    assert task.occurs_on(date(2026, 1, 16)) is True
    assert task.occurs_on(date(2026, 1, 17)) is True
    assert task.occurs_on(date(2026, 1, 20)) is True


def test_task_weekly_recurrence(tmp_path: Path) -> None:
    """Weekly tasks occur every 7 days from due_date."""
    task = Task.create(
        "Weekly review",
        order=0,
        status=TaskStatus.TODO,
        due_date=date(2026, 1, 15),  # Thursday
        repeat={"freq": "weekly", "interval": 1},
    )
    
    assert task.occurs_on(date(2026, 1, 15)) is True
    assert task.occurs_on(date(2026, 1, 22)) is True
    assert task.occurs_on(date(2026, 1, 29)) is True
    assert task.occurs_on(date(2026, 1, 16)) is False


def test_task_monthly_recurrence(tmp_path: Path) -> None:
    """Monthly tasks occur on same day of month."""
    task = Task.create(
        "Monthly invoice",
        order=0,
        status=TaskStatus.TODO,
        due_date=date(2026, 1, 15),
        repeat={"freq": "monthly", "interval": 1},
    )
    
    assert task.occurs_on(date(2026, 1, 15)) is True
    assert task.occurs_on(date(2026, 2, 15)) is True
    assert task.occurs_on(date(2026, 3, 15)) is True
    assert task.occurs_on(date(2026, 1, 16)) is False


def test_task_recurrence_respects_until(tmp_path: Path) -> None:
    """Task recurrence stops after 'until' date."""
    task = Task.create(
        "Limited daily",
        order=0,
        status=TaskStatus.TODO,
        due_date=date(2026, 1, 15),
        repeat={"freq": "daily", "interval": 1, "until": "2026-01-20"},
    )
    
    assert task.occurs_on(date(2026, 1, 20)) is True
    assert task.occurs_on(date(2026, 1, 21)) is False


def test_cycle_task_repeat_updates_frequency(tmp_path: Path) -> None:
    """Cycling task repeat updates the frequency correctly."""
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    
    task = Task.create(
        "Test task",
        order=0,
        status=TaskStatus.TODO,
        due_date=date(2026, 1, 15),
    )
    repo.upsert_task(task)
    
    # Initial: no repeat
    assert task.repeat is None or task.repeat.get("freq") == "none"
    
    # Cycle to daily
    updated = cycle_task_repeat(repo, task.id)
    assert updated.repeat == {"freq": "daily"}
    
    # Reload and cycle to weekly
    updated = cycle_task_repeat(repo, updated.id)
    assert updated.repeat == {"freq": "weekly"}
    
    # Reload and cycle to monthly
    updated = cycle_task_repeat(repo, updated.id)
    assert updated.repeat == {"freq": "monthly"}
    
    # Reload and cycle back to none
    updated = cycle_task_repeat(repo, updated.id)
    assert updated.repeat == {"freq": "none"}


def test_task_next_occurrence(tmp_path: Path) -> None:
    """Task.next_occurrence() calculates next due date."""
    task = Task.create(
        "Weekly task",
        order=0,
        status=TaskStatus.TODO,
        due_date=date(2026, 1, 15),
        repeat={"freq": "weekly", "interval": 1},
    )
    
    # Next occurrence after Jan 15 is Jan 22
    assert task.next_occurrence(date(2026, 1, 15)) == date(2026, 1, 22)
    assert task.next_occurrence(date(2026, 1, 20)) == date(2026, 1, 22)
    assert task.next_occurrence(date(2026, 1, 22)) == date(2026, 1, 29)


def test_task_next_occurrence_without_due_date(tmp_path: Path) -> None:
    """Task without due_date has no next occurrence."""
    task = Task.create(
        "Someday task",
        order=0,
        status=TaskStatus.TODO,
        due_date=None,
        repeat={"freq": "daily", "interval": 1},
    )
    
    assert task.next_occurrence(date(2026, 1, 15)) is None
