"""Tests for note reordering functionality (tasks and events)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest

from logui.domain.entities.event import Event
from logui.domain.entities.task import Task, TaskStatus
from logui.domain.errors import ValidationError
from logui.infrastructure.repositories.events_repo_json import JsonEventRepository
from logui.infrastructure.repositories.tasks_repo_json import JsonTaskRepository
from logui.usecases.events import (
    add_event_note,
    move_event_note_down,
    move_event_note_up,
)
from logui.usecases.tasks import (
    add_task_note,
    move_task_note_down,
    move_task_note_up,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def test_move_task_note_up(tmp_path):
    """Test moving a task note up in the list."""
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    now = utc_now()
    
    # Create a task
    task = Task.create(
        title="Test Task",
        status=TaskStatus.TODO,
        priority=False,
        due_date=None,
        link=None,
        now=now,
    )
    repo.upsert_task(task)
    
    # Add three notes
    note1 = add_task_note(repo, task.id, "First note", now=now)
    note2 = add_task_note(repo, task.id, "Second note", now=now)
    note3 = add_task_note(repo, task.id, "Third note", now=now)
    
    # Get current order
    task = repo.list_tasks()[0]
    assert [n.text for n in task.notes] == ["First note", "Second note", "Third note"]
    
    # Move second note up
    result = move_task_note_up(repo, task.id, note2.id, now=now)
    assert result is True
    
    # Check new order
    task = repo.list_tasks()[0]
    assert [n.text for n in task.notes] == ["Second note", "First note", "Third note"]


def test_move_task_note_down(tmp_path):
    """Test moving a task note down in the list."""
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    now = utc_now()
    
    # Create a task
    task = Task.create(
        title="Test Task",
        status=TaskStatus.TODO,
        priority=False,
        due_date=None,
        link=None,
        now=now,
    )
    repo.upsert_task(task)
    
    # Add three notes
    note1 = add_task_note(repo, task.id, "First note", now=now)
    note2 = add_task_note(repo, task.id, "Second note", now=now)
    note3 = add_task_note(repo, task.id, "Third note", now=now)
    
    # Get current order
    task = repo.list_tasks()[0]
    assert [n.text for n in task.notes] == ["First note", "Second note", "Third note"]
    
    # Move second note down
    result = move_task_note_down(repo, task.id, note2.id, now=now)
    assert result is True
    
    # Check new order
    task = repo.list_tasks()[0]
    assert [n.text for n in task.notes] == ["First note", "Third note", "Second note"]


def test_move_task_note_up_at_boundary(tmp_path):
    """Test that moving the first note up returns False (no-op)."""
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    now = utc_now()
    
    # Create a task
    task = Task.create(
        title="Test Task",
        status=TaskStatus.TODO,
        priority=False,
        due_date=None,
        link=None,
        now=now,
    )
    repo.upsert_task(task)
    
    # Add two notes
    note1 = add_task_note(repo, task.id, "First note", now=now)
    note2 = add_task_note(repo, task.id, "Second note", now=now)
    
    # Try to move first note up (should be no-op)
    result = move_task_note_up(repo, task.id, note1.id, now=now)
    assert result is False
    
    # Order should remain unchanged
    task = repo.list_tasks()[0]
    assert [n.text for n in task.notes] == ["First note", "Second note"]


def test_move_task_note_down_at_boundary(tmp_path):
    """Test that moving the last note down returns False (no-op)."""
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    now = utc_now()
    
    # Create a task
    task = Task.create(
        title="Test Task",
        status=TaskStatus.TODO,
        priority=False,
        due_date=None,
        link=None,
        now=now,
    )
    repo.upsert_task(task)
    
    # Add two notes
    note1 = add_task_note(repo, task.id, "First note", now=now)
    note2 = add_task_note(repo, task.id, "Second note", now=now)
    
    # Try to move last note down (should be no-op)
    result = move_task_note_down(repo, task.id, note2.id, now=now)
    assert result is False
    
    # Order should remain unchanged
    task = repo.list_tasks()[0]
    assert [n.text for n in task.notes] == ["First note", "Second note"]


def test_move_task_note_nonexistent_note(tmp_path):
    """Test that moving a non-existent note returns False."""
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    now = utc_now()
    
    # Create a task with one note
    task = Task.create(
        title="Test Task",
        status=TaskStatus.TODO,
        priority=False,
        due_date=None,
        link=None,
        now=now,
    )
    repo.upsert_task(task)
    add_task_note(repo, task.id, "First note", now=now)
    
    # Try to move a non-existent note
    fake_note_id = uuid4()
    result = move_task_note_up(repo, task.id, fake_note_id, now=now)
    assert result is False


def test_move_event_note_up(tmp_path):
    """Test moving an event note up in the list."""
    repo = JsonEventRepository(tmp_path / "events.json")
    now = utc_now()
    today = date.today()
    
    # Create an event
    event = Event.create(
        title="Test Event",
        day=today,
        now=now,
    )
    repo.upsert_event(event)
    
    # Add three notes
    add_event_note(repo, event.id, "First note", now=now)
    event = repo.get_event(event.id)
    note1_id = event.notes[0].id
    
    add_event_note(repo, event.id, "Second note", now=now)
    event = repo.get_event(event.id)
    note2_id = event.notes[1].id
    
    add_event_note(repo, event.id, "Third note", now=now)
    
    # Get current order
    event = repo.get_event(event.id)
    assert [n.text for n in event.notes] == ["First note", "Second note", "Third note"]
    
    # Move second note up
    event = move_event_note_up(repo, event.id, note2_id, now=now)
    
    # Check new order
    assert [n.text for n in event.notes] == ["Second note", "First note", "Third note"]


def test_move_event_note_down(tmp_path):
    """Test moving an event note down in the list."""
    repo = JsonEventRepository(tmp_path / "events.json")
    now = utc_now()
    today = date.today()
    
    # Create an event
    event = Event.create(
        title="Test Event",
        day=today,
        now=now,
    )
    repo.upsert_event(event)
    
    # Add three notes
    add_event_note(repo, event.id, "First note", now=now)
    event = repo.get_event(event.id)
    note1_id = event.notes[0].id
    
    add_event_note(repo, event.id, "Second note", now=now)
    event = repo.get_event(event.id)
    note2_id = event.notes[1].id
    
    add_event_note(repo, event.id, "Third note", now=now)
    
    # Get current order
    event = repo.get_event(event.id)
    assert [n.text for n in event.notes] == ["First note", "Second note", "Third note"]
    
    # Move second note down
    event = move_event_note_down(repo, event.id, note2_id, now=now)
    
    # Check new order
    assert [n.text for n in event.notes] == ["First note", "Third note", "Second note"]


def test_move_event_note_at_boundaries(tmp_path):
    """Test that moving notes at boundaries doesn't change order."""
    repo = JsonEventRepository(tmp_path / "events.json")
    now = utc_now()
    today = date.today()
    
    # Create an event
    event = Event.create(
        title="Test Event",
        day=today,
        now=now,
    )
    repo.upsert_event(event)
    
    # Add two notes
    add_event_note(repo, event.id, "First note", now=now)
    event = repo.get_event(event.id)
    note1_id = event.notes[0].id
    
    add_event_note(repo, event.id, "Second note", now=now)
    event = repo.get_event(event.id)
    note2_id = event.notes[1].id
    
    # Try to move first note up (should be no-op)
    event = move_event_note_up(repo, event.id, note1_id, now=now)
    assert [n.text for n in event.notes] == ["First note", "Second note"]
    
    # Try to move last note down (should be no-op)
    event = move_event_note_down(repo, event.id, note2_id, now=now)
    assert [n.text for n in event.notes] == ["First note", "Second note"]


def test_move_event_note_nonexistent(tmp_path):
    """Test that moving a non-existent event note raises ValidationError."""
    repo = JsonEventRepository(tmp_path / "events.json")
    now = utc_now()
    today = date.today()
    
    # Create an event with one note
    event = Event.create(
        title="Test Event",
        day=today,
        now=now,
    )
    repo.upsert_event(event)
    add_event_note(repo, event.id, "First note", now=now)
    
    # Try to move a non-existent note
    fake_note_id = uuid4()
    with pytest.raises(ValidationError, match="Note not found"):
        move_event_note_up(repo, event.id, fake_note_id, now=now)


def test_move_task_note_in_subtask(tmp_path):
    """Test moving notes in a subtask."""
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    now = utc_now()
    
    # Create parent task
    parent = Task.create(
        title="Parent Task",
        status=TaskStatus.TODO,
        priority=False,
        due_date=None,
        link=None,
        now=now,
    )
    repo.upsert_task(parent)
    
    # Create subtask
    subtask = Task.create(
        title="Subtask",
        status=TaskStatus.TODO,
        priority=False,
        due_date=None,
        link=None,
        now=now,
    )
    parent.add_subtask(subtask)
    repo.upsert_task(parent)
    
    # Add notes to subtask
    note1 = add_task_note(repo, subtask.id, "Subtask note 1", now=now)
    note2 = add_task_note(repo, subtask.id, "Subtask note 2", now=now)
    
    # Get current order
    parent = repo.list_tasks()[0]
    subtask = parent.subtasks[0]
    assert [n.text for n in subtask.notes] == ["Subtask note 1", "Subtask note 2"]
    
    # Move second note up
    result = move_task_note_up(repo, subtask.id, note2.id, now=now)
    assert result is True
    
    # Check new order
    parent = repo.list_tasks()[0]
    subtask = parent.subtasks[0]
    assert [n.text for n in subtask.notes] == ["Subtask note 2", "Subtask note 1"]
