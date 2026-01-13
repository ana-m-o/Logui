"""Tests for log functionality with completed subtasks."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from logui.domain.entities.task import Task, TaskStatus
from logui.ui.screens.log import _collect_all_completed_tasks


def test_collect_all_completed_tasks_includes_subtasks():
    """Test that _collect_all_completed_tasks collects completed subtasks."""
    now = datetime.now(timezone.utc)
    
    # Create a parent task (not completed)
    parent = Task(
        id=uuid4(),
        order=0,
        title="Parent Task",
        status=TaskStatus.IN_PROGRESS,
        priority=False,
        due_date=None,
        link=None,
        notes=[],
        subtasks=[],
        completed_at=None,
        created_at=now,
        updated_at=now,
    )
    
    # Create a completed subtask
    completed_subtask = Task(
        id=uuid4(),
        order=0,
        title="Completed Subtask",
        status=TaskStatus.DONE,
        priority=False,
        due_date=None,
        link=None,
        notes=[],
        subtasks=[],
        completed_at=now,
        created_at=now,
        updated_at=now,
    )
    
    parent.subtasks.append(completed_subtask)
    
    # Collect all completed tasks
    result = _collect_all_completed_tasks([parent])
    
    # Should only include the completed subtask, not the parent
    assert len(result) == 1
    assert result[0].id == completed_subtask.id
    assert result[0].title == "Completed Subtask"


def test_collect_all_completed_tasks_includes_parent_and_subtasks():
    """Test that both completed parent and completed subtasks are collected."""
    now = datetime.now(timezone.utc)
    
    # Create a completed parent task
    parent = Task(
        id=uuid4(),
        order=0,
        title="Completed Parent",
        status=TaskStatus.DONE,
        priority=False,
        due_date=None,
        link=None,
        notes=[],
        subtasks=[],
        completed_at=now,
        created_at=now,
        updated_at=now,
    )
    
    # Create a completed subtask
    completed_subtask = Task(
        id=uuid4(),
        order=0,
        title="Completed Subtask",
        status=TaskStatus.DONE,
        priority=False,
        due_date=None,
        link=None,
        notes=[],
        subtasks=[],
        completed_at=now,
        created_at=now,
        updated_at=now,
    )
    
    # Create an incomplete subtask
    incomplete_subtask = Task(
        id=uuid4(),
        order=1,
        title="Incomplete Subtask",
        status=TaskStatus.TODO,
        priority=False,
        due_date=None,
        link=None,
        notes=[],
        subtasks=[],
        completed_at=None,
        created_at=now,
        updated_at=now,
    )
    
    parent.subtasks.extend([completed_subtask, incomplete_subtask])
    
    # Collect all completed tasks
    result = _collect_all_completed_tasks([parent])
    
    # Should include both parent and completed subtask, but not incomplete subtask
    assert len(result) == 2
    result_ids = {t.id for t in result}
    assert parent.id in result_ids
    assert completed_subtask.id in result_ids
    assert incomplete_subtask.id not in result_ids


def test_collect_all_completed_tasks_deep_nesting():
    """Test that deeply nested completed subtasks are collected."""
    now = datetime.now(timezone.utc)
    
    # Create a parent task (not completed)
    parent = Task(
        id=uuid4(),
        order=0,
        title="Parent",
        status=TaskStatus.IN_PROGRESS,
        priority=False,
        due_date=None,
        link=None,
        notes=[],
        subtasks=[],
        completed_at=None,
        created_at=now,
        updated_at=now,
    )
    
    # Create a subtask (not completed)
    subtask = Task(
        id=uuid4(),
        order=0,
        title="Subtask",
        status=TaskStatus.IN_PROGRESS,
        priority=False,
        due_date=None,
        link=None,
        notes=[],
        subtasks=[],
        completed_at=None,
        created_at=now,
        updated_at=now,
    )
    
    # Create a deeply nested completed sub-subtask
    completed_sub_subtask = Task(
        id=uuid4(),
        order=0,
        title="Completed Sub-subtask",
        status=TaskStatus.DONE,
        priority=False,
        due_date=None,
        link=None,
        notes=[],
        subtasks=[],
        completed_at=now,
        created_at=now,
        updated_at=now,
    )
    
    subtask.subtasks.append(completed_sub_subtask)
    parent.subtasks.append(subtask)
    
    # Collect all completed tasks
    result = _collect_all_completed_tasks([parent])
    
    # Should include the deeply nested completed sub-subtask
    assert len(result) == 1
    assert result[0].id == completed_sub_subtask.id
    assert result[0].title == "Completed Sub-subtask"


def test_collect_all_completed_tasks_multiple_roots():
    """Test collection across multiple root tasks."""
    now = datetime.now(timezone.utc)
    
    # Create first root task (completed)
    root1 = Task(
        id=uuid4(),
        order=0,
        title="Root 1",
        status=TaskStatus.DONE,
        priority=False,
        due_date=None,
        link=None,
        notes=[],
        subtasks=[],
        completed_at=now,
        created_at=now,
        updated_at=now,
    )
    
    # Create second root task (not completed) with completed subtask
    root2 = Task(
        id=uuid4(),
        order=1,
        title="Root 2",
        status=TaskStatus.TODO,
        priority=False,
        due_date=None,
        link=None,
        notes=[],
        subtasks=[],
        completed_at=None,
        created_at=now,
        updated_at=now,
    )
    
    completed_subtask = Task(
        id=uuid4(),
        order=0,
        title="Completed Subtask of Root 2",
        status=TaskStatus.DONE,
        priority=False,
        due_date=None,
        link=None,
        notes=[],
        subtasks=[],
        completed_at=now,
        created_at=now,
        updated_at=now,
    )
    
    root2.subtasks.append(completed_subtask)
    
    # Collect all completed tasks
    result = _collect_all_completed_tasks([root1, root2])
    
    # Should include both root1 and the completed subtask of root2
    assert len(result) == 2
    result_ids = {t.id for t in result}
    assert root1.id in result_ids
    assert completed_subtask.id in result_ids
    assert root2.id not in result_ids


def test_collect_all_completed_tasks_empty_list():
    """Test that empty list returns empty list."""
    result = _collect_all_completed_tasks([])
    assert result == []


def test_collect_all_completed_tasks_no_completed():
    """Test that list with no completed tasks returns empty list."""
    now = datetime.now(timezone.utc)
    
    task = Task(
        id=uuid4(),
        order=0,
        title="Incomplete Task",
        status=TaskStatus.TODO,
        priority=False,
        due_date=None,
        link=None,
        notes=[],
        subtasks=[],
        completed_at=None,
        created_at=now,
        updated_at=now,
    )
    
    result = _collect_all_completed_tasks([task])
    assert result == []
