"""Test that subtasks cannot have subtasks (max depth is 2 levels)."""

import pytest

from logui.infrastructure.repositories.tasks_repo_json import JsonTaskRepository
from logui.usecases.tasks import CreateTaskInput, create_subtask, create_task


@pytest.fixture
def tasks_repo(tmp_path):
    """Create a temporary tasks repository."""
    return JsonTaskRepository(tmp_path / "tasks.json")


def test_create_subtask_of_subtask_creates_sibling(tasks_repo):
    """
    Test that creating a subtask of a subtask actually creates a sibling subtask.
    
    Structure:
    Root Task
      └─ Subtask 1
      
    When pressing 's' on Subtask 1, should create Subtask 2 (sibling), not a child.
    
    Final structure:
    Root Task
      ├─ Subtask 1
      └─ Subtask 2 (newly created)
    """
    # Create a root task
    root_data = CreateTaskInput(title="Root Task")
    root = create_task(tasks_repo, root_data)
    
    # Create a subtask
    subtask_data = CreateTaskInput(title="Subtask 1")
    subtask = create_subtask(tasks_repo, root.id, subtask_data)
    
    # Reload root from repo to get updated state
    from logui.usecases.tasks import get_task_by_id
    root_updated = get_task_by_id(tasks_repo, root.id)
    
    # Verify the structure so far
    assert len(root_updated.subtasks) == 1
    assert root_updated.subtasks[0].id == subtask.id
    assert len(subtask.subtasks) == 0  # Subtask has no children
    
    # Now try to create a "subtask" of the subtask
    new_subtask_data = CreateTaskInput(title="Subtask 2")
    new_subtask = create_subtask(tasks_repo, subtask.id, new_subtask_data)
    
    # Verify: new_subtask should be a sibling of subtask, not a child
    # (i.e., it's a subtask of root, not of subtask)
    assert len(subtask.subtasks) == 0, "Subtask should not have children"
    
    # Reload root to get the updated state
    updated_root = get_task_by_id(tasks_repo, root.id)
    
    # Root should now have 2 subtasks
    assert len(updated_root.subtasks) == 2
    subtask_ids = {st.id for st in updated_root.subtasks}
    assert subtask.id in subtask_ids
    assert new_subtask.id in subtask_ids
    assert new_subtask.title == "Subtask 2"


def test_create_subtask_of_root_works_normally(tasks_repo):
    """
    Test that creating a subtask of a root task works as expected.
    """
    # Create a root task
    root_data = CreateTaskInput(title="Root Task")
    root = create_task(tasks_repo, root_data)
    
    # Create a subtask
    subtask_data = CreateTaskInput(title="Subtask 1", priority=True)
    subtask = create_subtask(tasks_repo, root.id, subtask_data)
    
    # Verify: subtask should be a direct child of root
    assert subtask.title == "Subtask 1"
    assert subtask.priority is True
    
    from logui.usecases.tasks import get_task_by_id
    updated_root = get_task_by_id(tasks_repo, root.id)
    assert len(updated_root.subtasks) == 1
    assert updated_root.subtasks[0].id == subtask.id
