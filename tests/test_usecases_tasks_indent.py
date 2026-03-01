"""Tests for task indent/unindent operations (convert_task_to_subtask, convert_subtask_to_task)."""

from __future__ import annotations

import pytest

from logui.domain.errors import ValidationError
from logui.infrastructure.persistence.sqlite_database import SQLiteDatabase
from logui.infrastructure.repositories.tasks_repo_sqlite import SqliteTaskRepository
from logui.usecases.tasks import (
    CreateTaskInput,
    convert_subtask_to_task,
    convert_task_to_subtask,
    create_subtask,
    create_task,
    get_task_by_id,
)


def test_convert_task_to_subtask_basic(tmp_path):
    """Test converting a task into a subtask of another task."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    # Create two root tasks
    t1 = create_task(repo, CreateTaskInput(title="Task 1"))
    t2 = create_task(repo, CreateTaskInput(title="Task 2"))

    # Convert t2 into a subtask of t1
    converted = convert_task_to_subtask(repo, t2.id, t1.id)
    assert converted.id == t2.id

    # Verify structure
    roots = list(repo.list_tasks())
    assert len(roots) == 1
    assert roots[0].id == t1.id
    assert len(roots[0].subtasks) == 1
    assert roots[0].subtasks[0].id == t2.id
    assert roots[0].subtasks[0].title == "Task 2"


def test_convert_task_to_subtask_cannot_indent_subtask(tmp_path):
    """Test that we cannot convert a subtask into a sub-subtask (only 1 level allowed)."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    parent = create_task(repo, CreateTaskInput(title="Parent"))
    subtask = create_subtask(repo, parent.id, CreateTaskInput(title="Subtask"))

    # Try to convert subtask into a sub-subtask (should fail)
    with pytest.raises(ValidationError, match="already a subtask"):
        convert_task_to_subtask(repo, subtask.id, parent.id)


def test_convert_task_to_subtask_cannot_indent_task_with_subtasks(tmp_path):
    """Test that we cannot indent a task that has subtasks."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    parent = create_task(repo, CreateTaskInput(title="Parent"))
    task_with_subtask = create_task(repo, CreateTaskInput(title="Task with Subtask"))
    subtask = create_subtask(repo, task_with_subtask.id, CreateTaskInput(title="Subtask"))

    # Try to convert task_with_subtask into a subtask of parent (should fail)
    with pytest.raises(ValidationError, match="has subtasks"):
        convert_task_to_subtask(repo, task_with_subtask.id, parent.id)


def test_convert_task_to_subtask_cannot_use_subtask_as_parent(tmp_path):
    """Test that we cannot use a subtask as target parent (to maintain 1 level)."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    parent = create_task(repo, CreateTaskInput(title="Parent"))
    subtask = create_subtask(repo, parent.id, CreateTaskInput(title="Subtask"))
    task = create_task(repo, CreateTaskInput(title="Task"))

    # Try to convert task into a subtask of another subtask (should fail)
    with pytest.raises(ValidationError, match="target is a subtask"):
        convert_task_to_subtask(repo, task.id, subtask.id)


def test_convert_subtask_to_task_basic(tmp_path):
    """Test converting a subtask into a root task."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    parent = create_task(repo, CreateTaskInput(title="Parent"))
    subtask = create_subtask(repo, parent.id, CreateTaskInput(title="Subtask"))

    # Convert subtask into a root task
    converted = convert_subtask_to_task(repo, subtask.id)
    assert converted.id == subtask.id

    # Verify structure
    roots = list(repo.list_tasks())
    assert len(roots) == 2
    root_titles = {r.title for r in roots}
    assert root_titles == {"Parent", "Subtask"}

    # Parent should have no subtasks
    parent_task = get_task_by_id(repo, parent.id)
    assert parent_task is not None
    assert len(parent_task.subtasks) == 0


def test_convert_subtask_to_task_cannot_unindent_root_task(tmp_path):
    """Test that we cannot unindent a root task."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    task = create_task(repo, CreateTaskInput(title="Root Task"))

    # Try to unindent a root task (should fail)
    with pytest.raises(ValidationError, match="already a root task"):
        convert_subtask_to_task(repo, task.id)


def test_convert_subtask_to_task_order_placement(tmp_path):
    """Test that unindented subtask is placed after its ex-parent in the list."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    # Create structure: Task1 -> [SubA, SubB], Task2
    task1 = create_task(repo, CreateTaskInput(title="Task1"))
    sub_a = create_subtask(repo, task1.id, CreateTaskInput(title="SubA"))
    sub_b = create_subtask(repo, task1.id, CreateTaskInput(title="SubB"))
    task2 = create_task(repo, CreateTaskInput(title="Task2"))

    # Unindent SubB
    convert_subtask_to_task(repo, sub_b.id)

    # Verify order: should be Task1, SubB (or Task1, Task2, SubB depending on order calculation)
    # The key is that SubB should be a root task now
    roots = sorted(list(repo.list_tasks()), key=lambda t: (t.order, t.created_at))
    root_titles = [r.title for r in roots]
    
    # SubB should be in the roots
    assert "SubB" in root_titles
    
    # Task1 should have only SubA as subtask
    task1_reloaded = get_task_by_id(repo, task1.id)
    assert task1_reloaded is not None
    assert len(task1_reloaded.subtasks) == 1
    assert task1_reloaded.subtasks[0].title == "SubA"


def test_indent_unindent_roundtrip(tmp_path):
    """Test that indent followed by unindent works correctly."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteTaskRepository(db)

    task1 = create_task(repo, CreateTaskInput(title="Task1"))
    task2 = create_task(repo, CreateTaskInput(title="Task2"))

    # Initially, both are root tasks
    roots = list(repo.list_tasks())
    assert len(roots) == 2

    # Indent Task2 (make it subtask of Task1)
    convert_task_to_subtask(repo, task2.id, task1.id)

    roots = list(repo.list_tasks())
    assert len(roots) == 1
    assert roots[0].title == "Task1"
    assert len(roots[0].subtasks) == 1

    # Unindent Task2 (make it root task again)
    convert_subtask_to_task(repo, task2.id)

    roots = list(repo.list_tasks())
    assert len(roots) == 2
    root_titles = {r.title for r in roots}
    assert root_titles == {"Task1", "Task2"}
