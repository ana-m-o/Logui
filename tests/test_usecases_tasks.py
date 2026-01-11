from __future__ import annotations

from datetime import date

import pytest

from logui.domain.entities.task import TaskLink, TaskStatus
from logui.domain.errors import ValidationError
from logui.infrastructure.repositories.tasks_repo_json import JsonTaskRepository
from logui.usecases.tasks import (
    CreateTaskInput,
    UpdateTaskPatch,
    add_task_note,
    create_subtask,
    create_task,
    cycle_task_status,
    delete_task,
    delete_task_note,
    get_task_by_id,
    move_task_down,
    move_task_up,
    toggle_task_priority,
    update_task,
    update_task_note,
)


def test_create_task_persists_and_defaults_status(tmp_path) -> None:
    repo = JsonTaskRepository(tmp_path / "tasks.json")

    task = create_task(repo, CreateTaskInput(title="Tarea 1"))

    task2 = create_task(repo, CreateTaskInput(title="Tarea 2"))

    assert repo.get_task(task.id) is not None
    assert task.status == TaskStatus.TODO
    assert task.priority is False
    assert task.order == 0
    assert task2.order == 1


def test_create_task_with_due_date_inserts_before_tasks_without_due_date(tmp_path) -> None:
    repo = JsonTaskRepository(tmp_path / "tasks.json")

    create_task(repo, CreateTaskInput(title="A"))
    create_task(repo, CreateTaskInput(title="B"))

    due = create_task(repo, CreateTaskInput(title="D", due_date=date(2025, 12, 30)))

    assert [t.title for t in repo.list_tasks()] == ["D", "A", "B"]
    assert due.order == 0


def test_create_task_with_due_date_keeps_existing_due_date_tasks_above_boundary(tmp_path) -> None:
    repo = JsonTaskRepository(tmp_path / "tasks.json")

    x = create_task(repo, CreateTaskInput(title="X", due_date=date(2025, 12, 30)))
    a = create_task(repo, CreateTaskInput(title="A"))
    b = create_task(repo, CreateTaskInput(title="B"))

    y = create_task(repo, CreateTaskInput(title="Y", due_date=date(2025, 12, 31)))

    assert [t.title for t in repo.list_tasks()] == ["X", "Y", "A", "B"]
    # Orders are persisted via updated copies; reload to assert final state.
    x2 = repo.get_task(x.id)
    y2 = repo.get_task(y.id)
    a2 = repo.get_task(a.id)
    b2 = repo.get_task(b.id)
    assert x2 is not None and x2.order == 0
    assert y2 is not None and y2.order == 1
    assert a2 is not None and a2.order == 2
    assert b2 is not None and b2.order == 3


def test_toggle_task_priority(tmp_path) -> None:
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    task = create_task(repo, CreateTaskInput(title="Tarea 1", priority=False))

    updated = toggle_task_priority(repo, task.id)
    assert updated.priority is True
    assert updated.order == task.order


def test_cycle_task_status_wraps(tmp_path) -> None:
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    task = create_task(repo, CreateTaskInput(title="Tarea 1", status=TaskStatus.DONE))

    updated = cycle_task_status(repo, task.id)
    assert updated.status == TaskStatus.TODO
    assert updated.order == task.order


def test_update_task_can_set_and_clear_due_date(tmp_path) -> None:
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    task = create_task(repo, CreateTaskInput(title="Tarea 1"))

    updated = update_task(repo, task.id, UpdateTaskPatch(due_date=date(2025, 12, 25)))
    assert updated.due_date == date(2025, 12, 25)
    assert updated.order == task.order

    updated2 = update_task(repo, task.id, UpdateTaskPatch(due_date=None))
    assert updated2.due_date is None
    assert updated2.order == task.order


def test_update_task_can_set_and_clear_link(tmp_path) -> None:
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    task = create_task(repo, CreateTaskInput(title="Tarea 1"))

    updated = update_task(
        repo,
        task.id,
        UpdateTaskPatch(link=TaskLink.create("https://example.com", text="Example")),
    )
    assert updated.link is not None
    assert updated.link.url == "https://example.com"
    assert updated.link.text == "Example"

    updated2 = update_task(repo, task.id, UpdateTaskPatch(link=None))
    assert updated2.link is None


def test_update_task_sets_due_date_and_type(tmp_path) -> None:
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    task = create_task(repo, CreateTaskInput(title="Tarea 1"))

    updated = update_task(
        repo,
        task.id,
        UpdateTaskPatch(due_date=date(2025, 12, 25)),
    )

    assert updated.due_date == date(2025, 12, 25)


def test_move_task_up_swaps_order_with_previous(tmp_path) -> None:
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    create_task(repo, CreateTaskInput(title="A"))
    create_task(repo, CreateTaskInput(title="B"))
    c = create_task(repo, CreateTaskInput(title="C"))

    moved = move_task_up(repo, c.id)
    assert moved.id == c.id

    titles = [t.title for t in repo.list_tasks()]
    assert titles == ["A", "C", "B"]


def test_move_task_down_swaps_order_with_next(tmp_path) -> None:
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    a = create_task(repo, CreateTaskInput(title="A"))
    create_task(repo, CreateTaskInput(title="B"))
    _c = create_task(repo, CreateTaskInput(title="C"))

    moved = move_task_down(repo, a.id)
    assert moved.id == a.id

    titles = [t.title for t in repo.list_tasks()]
    assert titles == ["B", "A", "C"]


def test_move_task_at_boundaries_is_noop(tmp_path) -> None:
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    a = create_task(repo, CreateTaskInput(title="A"))
    b = create_task(repo, CreateTaskInput(title="B"))

    moved_up = move_task_up(repo, a.id)
    assert moved_up.order == a.order
    assert [t.title for t in repo.list_tasks()] == ["A", "B"]

    moved_down = move_task_down(repo, b.id)
    assert moved_down.order == b.order
    assert [t.title for t in repo.list_tasks()] == ["A", "B"]


def test_move_subtask_up_swaps_order_with_previous_sibling(tmp_path) -> None:
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    parent = create_task(repo, CreateTaskInput(title="Parent"))

    _a = create_subtask(repo, parent.id, CreateTaskInput(title="A"))
    _b = create_subtask(repo, parent.id, CreateTaskInput(title="B"))
    c = create_subtask(repo, parent.id, CreateTaskInput(title="C"))

    moved = move_task_up(repo, c.id)
    assert moved.id == c.id

    loaded_parent = get_task_by_id(repo, parent.id)
    assert loaded_parent is not None
    titles = [
        t.title for t in sorted(loaded_parent.subtasks, key=lambda t: (t.order, t.created_at))
    ]
    assert titles == ["A", "C", "B"]


def test_move_subtask_down_swaps_order_with_next_sibling(tmp_path) -> None:
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    parent = create_task(repo, CreateTaskInput(title="Parent"))

    a = create_subtask(repo, parent.id, CreateTaskInput(title="A"))
    _b = create_subtask(repo, parent.id, CreateTaskInput(title="B"))
    _c = create_subtask(repo, parent.id, CreateTaskInput(title="C"))

    moved = move_task_down(repo, a.id)
    assert moved.id == a.id

    loaded_parent = get_task_by_id(repo, parent.id)
    assert loaded_parent is not None
    titles = [
        t.title for t in sorted(loaded_parent.subtasks, key=lambda t: (t.order, t.created_at))
    ]
    assert titles == ["B", "A", "C"]


def test_move_subtask_at_boundaries_is_noop(tmp_path) -> None:
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    parent = create_task(repo, CreateTaskInput(title="Parent"))

    a = create_subtask(repo, parent.id, CreateTaskInput(title="A"))
    b = create_subtask(repo, parent.id, CreateTaskInput(title="B"))

    moved_up = move_task_up(repo, a.id)
    assert moved_up.id == a.id

    moved_down = move_task_down(repo, b.id)
    assert moved_down.id == b.id

    loaded_parent = get_task_by_id(repo, parent.id)
    assert loaded_parent is not None
    titles = [
        t.title for t in sorted(loaded_parent.subtasks, key=lambda t: (t.order, t.created_at))
    ]
    assert titles == ["A", "B"]


def test_create_subtask_persists_under_parent(tmp_path) -> None:
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    parent = create_task(repo, CreateTaskInput(title="Parent"))

    s1 = create_subtask(repo, parent.id, CreateTaskInput(title="Child 1"))
    s2 = create_subtask(repo, parent.id, CreateTaskInput(title="Child 2"))

    roots = list(repo.list_tasks())
    assert len(roots) == 1
    assert roots[0].title == "Parent"
    assert [t.title for t in roots[0].subtasks] == ["Child 1", "Child 2"]
    assert roots[0].subtasks[0].order == 0
    assert roots[0].subtasks[1].order == 1

    assert get_task_by_id(repo, s1.id) is not None
    assert get_task_by_id(repo, s2.id) is not None


def test_create_subtask_persists_link(tmp_path) -> None:
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    parent = create_task(repo, CreateTaskInput(title="Parent"))

    s1 = create_subtask(
        repo,
        parent.id,
        CreateTaskInput(
            title="Child 1",
            link=TaskLink.create("https://example.com", text="Example"),
        ),
    )

    loaded = get_task_by_id(repo, s1.id)
    assert loaded is not None
    assert loaded.link is not None
    assert loaded.link.url == "https://example.com"
    assert loaded.link.text == "Example"


def test_create_subtask_with_due_date_inserts_before_siblings_without_due_date(tmp_path) -> None:
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    parent = create_task(repo, CreateTaskInput(title="Parent"))

    a = create_subtask(repo, parent.id, CreateTaskInput(title="A"))
    b = create_subtask(repo, parent.id, CreateTaskInput(title="B"))
    d = create_subtask(repo, parent.id, CreateTaskInput(title="D", due_date=date(2025, 12, 30)))

    loaded = get_task_by_id(repo, parent.id)
    assert loaded is not None
    titles = [t.title for t in sorted(loaded.subtasks, key=lambda t: (t.order, t.created_at))]
    assert titles == ["D", "A", "B"]

    # Orders are updated on siblings; reload to assert final state.
    a2 = get_task_by_id(repo, a.id)
    b2 = get_task_by_id(repo, b.id)
    d2 = get_task_by_id(repo, d.id)
    assert d2 is not None and d2.order == 0
    assert a2 is not None and a2.order == 1
    assert b2 is not None and b2.order == 2


def test_update_and_delete_subtask(tmp_path) -> None:
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    parent = create_task(repo, CreateTaskInput(title="Parent"))
    sub = create_subtask(repo, parent.id, CreateTaskInput(title="Child"))

    updated = update_task(repo, sub.id, UpdateTaskPatch(title="Child (edited)"))
    assert updated.title == "Child (edited)"

    roots = list(repo.list_tasks())
    assert roots[0].subtasks[0].title == "Child (edited)"

    assert delete_task(repo, sub.id) is True
    roots2 = list(repo.list_tasks())
    assert roots2[0].subtasks == []

    assert delete_task(repo, sub.id) is False


def test_task_notes_crud_on_subtask(tmp_path) -> None:
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    parent = create_task(repo, CreateTaskInput(title="Parent"))
    sub = create_subtask(repo, parent.id, CreateTaskInput(title="Child"))

    note = add_task_note(repo, sub.id, "Primera")
    loaded = get_task_by_id(repo, sub.id)
    assert loaded is not None
    assert len(loaded.notes) == 1
    assert loaded.notes[0].id == note.id
    assert loaded.notes[0].text == "Primera"

    updated = update_task_note(repo, sub.id, note.id, "Editada")
    assert updated.id == note.id
    assert updated.text == "Editada"

    loaded2 = get_task_by_id(repo, sub.id)
    assert loaded2 is not None
    assert loaded2.notes[0].text == "Editada"

    assert delete_task_note(repo, sub.id, note.id) is True
    loaded3 = get_task_by_id(repo, sub.id)
    assert loaded3 is not None
    assert loaded3.notes == []

    assert delete_task_note(repo, sub.id, note.id) is False


def test_add_empty_task_note_rejected(tmp_path) -> None:
    repo = JsonTaskRepository(tmp_path / "tasks.json")
    task = create_task(repo, CreateTaskInput(title="T"))

    with pytest.raises(ValidationError):
        add_task_note(repo, task.id, "   ")
