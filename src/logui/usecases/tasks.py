from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from uuid import UUID

from logui.domain.entities.task import Task, TaskLink, TaskNote, TaskStatus, utc_now
from logui.domain.errors import ValidationError
from logui.domain.ports.tasks import TaskRepository


@dataclass(frozen=True)
class CreateTaskInput:
    title: str
    status: TaskStatus = TaskStatus.TODO
    priority: bool = False
    due_date: date | None = None
    link: TaskLink | None = None


_MISSING = object()


@dataclass(frozen=True)
class UpdateTaskPatch:
    title: str | object = _MISSING
    status: TaskStatus | object = _MISSING
    priority: bool | object = _MISSING
    due_date: date | None | object = _MISSING
    link: TaskLink | None | object = _MISSING


_STATUS_CYCLE = [
    TaskStatus.TODO,
    TaskStatus.IN_PROGRESS,
    TaskStatus.POSTPONED,
    TaskStatus.IN_REVIEW,
    TaskStatus.DONE,
]

_REPEAT_CYCLE = ["none", "daily", "weekly", "monthly"]


def list_tasks(repo: TaskRepository) -> list[Task]:
    return list(repo.list_tasks())


def get_task_by_id(repo: TaskRepository, task_id: UUID) -> Task | None:
    try:
        _root, task, _parent = _find_root_and_task(repo, task_id)
        return task
    except ValidationError:
        return None


def _clone_task(task: Task) -> Task:
    return Task(
        id=task.id,
        order=task.order,
        title=task.title,
        status=task.status,
        priority=task.priority,
        due_date=task.due_date,
        link=task.link,
        notes=list(task.notes),
        subtasks=[_clone_task(t) for t in task.subtasks],
        completed_at=task.completed_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
        repeat=task.repeat,
    )


def _find_task_in_tree(
    root: Task, task_id: UUID, *, parent: Task | None = None
) -> tuple[Task, Task | None] | None:
    if root.id == task_id:
        return root, parent
    for st in root.subtasks:
        found = _find_task_in_tree(st, task_id, parent=root)
        if found is not None:
            return found
    return None


def _find_root_and_task(repo: TaskRepository, task_id: UUID) -> tuple[Task, Task, Task | None]:
    roots = [_clone_task(t) for t in repo.list_tasks()]
    for root in roots:
        found = _find_task_in_tree(root, task_id)
        if found is not None:
            task, parent = found
            return root, task, parent
    raise ValidationError("Task not found")


def create_task(
    repo: TaskRepository,
    data: CreateTaskInput,
    *,
    now: datetime | None = None,
) -> Task:
    existing = sorted(repo.list_tasks(), key=lambda t: (t.order, t.created_at))

    next_order = 0
    if existing:
        next_order = max(t.order for t in existing) + 1

    # Default insertion rule:
    # - Tasks *with* due date should appear above tasks *without* due date.
    # - But the user can still reorder later (we encode this by choosing the
    #   initial `order`, rather than applying a dynamic sort).
    if data.due_date is not None and existing:
        first_without_due = next((t for t in existing if t.due_date is None), None)
        if first_without_due is not None:
            insert_order = first_without_due.order
            # Shift existing tasks down to make room.
            for t in sorted(existing, key=lambda t: t.order, reverse=True):
                if t.order < insert_order:
                    continue
                shifted = _clone_task(t)
                shifted.order = t.order + 1
                shifted._validate_invariants()  # noqa: SLF001
                shifted.touch(now=now)
                repo.upsert_task(shifted)
            next_order = insert_order

    task = Task.create(
        data.title,
        now=now,
        order=next_order,
        status=data.status,
        priority=data.priority,
        due_date=data.due_date,
        link=data.link,
    )
    repo.upsert_task(task)
    return task


def update_task(
    repo: TaskRepository,
    task_id: UUID,
    patch: UpdateTaskPatch,
    *,
    now: datetime | None = None,
) -> Task:
    root, existing, _parent = _find_root_and_task(repo, task_id)

    existing_title = existing.title
    existing_status = existing.status
    existing_priority = existing.priority
    existing_due = existing.due_date
    existing_link = existing.link

    existing.title = existing_title if patch.title is _MISSING else str(patch.title)
    new_status = existing_status if patch.status is _MISSING else TaskStatus(patch.status)
    existing.status = new_status

    # Maintain completed_at semantics.
    if new_status == TaskStatus.DONE and existing_status != TaskStatus.DONE:
        existing.completed_at = now or utc_now()
    elif new_status != TaskStatus.DONE and existing_status == TaskStatus.DONE:
        existing.completed_at = None
    existing.priority = existing_priority if patch.priority is _MISSING else bool(patch.priority)
    existing.due_date = existing_due if patch.due_date is _MISSING else patch.due_date
    existing.link = existing_link if patch.link is _MISSING else patch.link

    existing._validate_invariants()  # noqa: SLF001
    existing.touch(now=now)
    root.touch(now=now)
    repo.upsert_task(root)
    return existing


def delete_task(repo: TaskRepository, task_id: UUID) -> bool:
    # Root delete
    if repo.delete_task(task_id):
        return True

    # Nested delete
    try:
        root, _existing, parent = _find_root_and_task(repo, task_id)
    except ValidationError:
        return False
    if parent is None:
        return False
    parent.subtasks = [t for t in parent.subtasks if t.id != task_id]
    parent.touch()
    root.touch()
    repo.upsert_task(root)
    return True


def toggle_task_priority(
    repo: TaskRepository,
    task_id: UUID,
    *,
    now: datetime | None = None,
) -> Task:
    root, task, _parent = _find_root_and_task(repo, task_id)
    task.priority = not task.priority
    task._validate_invariants()  # noqa: SLF001
    task.touch(now=now)
    root.touch(now=now)
    repo.upsert_task(root)
    return task


def cycle_task_status(
    repo: TaskRepository,
    task_id: UUID,
    *,
    now: datetime | None = None,
) -> Task:
    root, task, parent = _find_root_and_task(repo, task_id)

    try:
        idx = _STATUS_CYCLE.index(task.status)
    except ValueError:
        idx = 0

    next_status = _STATUS_CYCLE[(idx + 1) % len(_STATUS_CYCLE)]

    prev_status = task.status
    task.status = next_status

    if next_status == TaskStatus.DONE and prev_status != TaskStatus.DONE:
        actual_now = now or utc_now()
        task.completed_at = actual_now

        # If task has recurrence but no due_date, auto-assign due_date to today
        if task.repeat and isinstance(task.repeat, dict) and task.due_date is None:
            freq = task.repeat.get("freq")
            if freq and freq != "none":
                task.due_date = actual_now.astimezone().date()

        # If task has recurrence and due_date, clone it for the next occurrence
        if task.repeat and isinstance(task.repeat, dict) and task.due_date:
            freq = task.repeat.get("freq")
            if freq and freq != "none":
                next_due = task.next_occurrence(after=task.due_date)
                if next_due is not None:
                    # Create a new task for the next occurrence
                    new_task = Task.create(
                        title=task.title,
                        status=TaskStatus.TODO,
                        priority=task.priority,
                        due_date=next_due,
                        link=task.link,
                    )
                    new_task.repeat = dict(task.repeat)
                    new_task.notes = list(task.notes)

                    # Clone subtasks recursively
                    for subtask in task.subtasks:
                        new_subtask = Task.create(
                            title=subtask.title,
                            status=TaskStatus.TODO,
                            priority=subtask.priority,
                            due_date=subtask.due_date,
                            link=subtask.link,
                        )
                        new_subtask.notes = list(subtask.notes)
                        new_task.subtasks.append(new_subtask)

                    # Calculate order: place after the current task with better precision
                    new_task.order = task.order + 0.5
                    
                    # Note: In the future, if tasks are positioned very close together,
                    # calling normalize_task_order() can help maintain clean values

                    # Add to parent or root level
                    if parent is not None:
                        parent.subtasks.append(new_task)
                    else:
                        # Task is at root level, need to add it separately
                        # First save the current task as DONE
                        repo.upsert_task(root)
                        # Then insert the new task
                        repo.upsert_task(new_task)
                        task._validate_invariants()  # noqa: SLF001
                        task.touch(now=now)
                        root.touch(now=now)
                        return task

    elif next_status != TaskStatus.DONE and prev_status == TaskStatus.DONE:
        task.completed_at = None

    task._validate_invariants()  # noqa: SLF001
    task.touch(now=now)
    root.touch(now=now)
    repo.upsert_task(root)
    return task


def move_task_up(
    repo: TaskRepository,
    task_id: UUID,
    *,
    now: datetime | None = None,
) -> Task:
    return _move_task(repo, task_id, direction=-1, now=now)


def move_task_down(
    repo: TaskRepository,
    task_id: UUID,
    *,
    now: datetime | None = None,
) -> Task:
    return _move_task(repo, task_id, direction=+1, now=now)


def cycle_task_repeat(
    repo: TaskRepository,
    task_id: UUID,
    *,
    now: datetime | None = None,
) -> Task:
    """Cycle through repeat frequencies for a task: none → daily → weekly → monthly.

    If activating repetition (from 'none' to any frequency) and the task has no due_date,
    automatically assigns due_date to today.
    """
    root, task, parent = _find_root_and_task(repo, task_id)

    current = "none"
    if task.repeat and isinstance(task.repeat, dict) and task.repeat.get("freq"):
        current = str(task.repeat.get("freq"))

    try:
        idx = _REPEAT_CYCLE.index(current)
    except ValueError:
        idx = 0

    next_freq = _REPEAT_CYCLE[(idx + 1) % len(_REPEAT_CYCLE)]

    # If activating repetition (from "none" to any frequency) and task has no due_date,
    # automatically assign due_date to today
    new_due_date = task.due_date
    if current == "none" and next_freq != "none" and task.due_date is None:
        actual_now = now or datetime.now(tz=timezone.utc)
        new_due_date = actual_now.astimezone().date()

    # Create a new Task instance with updated repeat field
    updated = Task(
        id=task.id,
        order=task.order,
        title=task.title,
        status=task.status,
        priority=task.priority,
        due_date=new_due_date,
        link=task.link,
        repeat={"freq": next_freq},
        notes=list(task.notes),
        subtasks=list(task.subtasks),
        completed_at=task.completed_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )

    updated.touch(now=now)

    # If this is a root task, just save it
    if parent is None:
        repo.upsert_task(updated)
        return updated

    # If it's a subtask, replace in parent's subtasks list
    parent.subtasks = [updated if t.id == task_id else t for t in parent.subtasks]
    parent.touch(now=now)
    root.touch(now=now)
    repo.upsert_task(root)
    return updated


def _move_task(
    repo: TaskRepository,
    task_id: UUID,
    *,
    direction: int,
    now: datetime | None = None,
) -> Task:
    if direction not in (-1, +1):
        raise ValueError("direction must be -1 or +1")

    # Root reorder: tasks are stored as independent roots.
    try:
        _root, _task, parent = _find_root_and_task(repo, task_id)
    except ValidationError:
        parent = None

    if parent is None:
        tasks = sorted(repo.list_tasks(), key=lambda t: (t.order, t.created_at))
        idx = next((i for i, t in enumerate(tasks) if t.id == task_id), None)
        if idx is None:
            raise ValidationError("Task not found")

        swap_idx = idx + direction
        if swap_idx < 0 or swap_idx >= len(tasks):
            return tasks[idx]

        a = tasks[idx]
        b = tasks[swap_idx]

        a2 = _clone_task(a)
        b2 = _clone_task(b)
        a2.order, b2.order = b.order, a.order
        a2._validate_invariants()  # noqa: SLF001
        b2._validate_invariants()  # noqa: SLF001
        a2.touch(now=now)
        b2.touch(now=now)

        repo.upsert_task(a2)
        repo.upsert_task(b2)
        return a2

    # Nested reorder: reorder within parent's subtasks and persist via the root.
    root, task, parent = _find_root_and_task(repo, task_id)

    siblings = sorted(parent.subtasks, key=lambda t: (t.order, t.created_at))
    idx = next((i for i, t in enumerate(siblings) if t.id == task_id), None)
    if idx is None:
        raise ValidationError("Task not found")

    swap_idx = idx + direction
    if swap_idx < 0 or swap_idx >= len(siblings):
        return task

    a = siblings[idx]
    b = siblings[swap_idx]

    a.order, b.order = b.order, a.order
    a._validate_invariants()  # noqa: SLF001
    b._validate_invariants()  # noqa: SLF001
    a.touch(now=now)
    b.touch(now=now)
    parent.touch(now=now)
    root.touch(now=now)
    repo.upsert_task(root)
    return task


def create_subtask(
    repo: TaskRepository,
    parent_id: UUID,
    data: CreateTaskInput,
    *,
    now: datetime | None = None,
) -> Task:
    root, requested_parent, grandparent = _find_root_and_task(repo, parent_id)

    # Redirect: if trying to create a subtask of a subtask,
    # create a sibling subtask instead
    if grandparent is not None:
        parent = grandparent
    else:
        parent = requested_parent

    siblings = sorted(parent.subtasks, key=lambda t: (t.order, t.created_at))

    next_order = 0
    if siblings:
        next_order = max(t.order for t in siblings) + 1

    # Default insertion rule for subtasks:
    # - Subtasks *with* due date should appear above subtasks *without* due date.
    # - Keep the ability to reorder later (we only choose initial `order`).
    if data.due_date is not None and siblings:
        first_without_due = next((t for t in siblings if t.due_date is None), None)
        if first_without_due is not None:
            insert_order = first_without_due.order
            for t in sorted(siblings, key=lambda t: t.order, reverse=True):
                if t.order < insert_order:
                    continue
                t.order = t.order + 1
                t._validate_invariants()  # noqa: SLF001
                t.touch(now=now)
            next_order = insert_order

    subtask = Task.create(
        data.title,
        now=now,
        order=next_order,
        status=data.status,
        priority=data.priority,
        due_date=data.due_date,
        link=data.link,
    )
    parent.add_subtask(subtask, now=now)
    root.touch(now=now)
    repo.upsert_task(root)
    return subtask


def add_task_note(
    repo: TaskRepository,
    task_id: UUID,
    text: str,
    *,
    now: datetime | None = None,
) -> TaskNote:
    root, task, _parent = _find_root_and_task(repo, task_id)
    note = task.add_note(text, now=now)
    root.touch(now=now)
    repo.upsert_task(root)
    return note


def update_task_note(
    repo: TaskRepository,
    task_id: UUID,
    note_id: UUID,
    text: str,
    *,
    now: datetime | None = None,
) -> TaskNote:
    root, task, _parent = _find_root_and_task(repo, task_id)
    cleaned = (text or "").strip()
    if not cleaned:
        raise ValidationError("Note text cannot be empty")

    note = next((n for n in task.notes if n.id == note_id), None)
    if note is None:
        raise ValidationError("Note not found")

    updated = TaskNote(id=note.id, text=cleaned, created_at=note.created_at)
    task.notes = [updated if n.id == note_id else n for n in task.notes]
    task.touch(now=now)
    root.touch(now=now)
    repo.upsert_task(root)
    return updated


def delete_task_note(
    repo: TaskRepository,
    task_id: UUID,
    note_id: UUID,
    *,
    now: datetime | None = None,
) -> bool:
    root, task, _parent = _find_root_and_task(repo, task_id)
    before = len(task.notes)
    task.notes = [n for n in task.notes if n.id != note_id]
    deleted = len(task.notes) != before
    if deleted:
        task.touch(now=now)
        root.touch(now=now)
        repo.upsert_task(root)
    return deleted


def move_task_note_up(
    repo: TaskRepository,
    task_id: UUID,
    note_id: UUID,
    *,
    now: datetime | None = None,
) -> bool:
    """Move a task note up in the list (towards the beginning)."""
    return _move_task_note(repo, task_id, note_id, direction=-1, now=now)


def move_task_note_down(
    repo: TaskRepository,
    task_id: UUID,
    note_id: UUID,
    *,
    now: datetime | None = None,
) -> bool:
    """Move a task note down in the list (towards the end)."""
    return _move_task_note(repo, task_id, note_id, direction=+1, now=now)


def _move_task_note(
    repo: TaskRepository,
    task_id: UUID,
    note_id: UUID,
    *,
    direction: int,
    now: datetime | None = None,
) -> bool:
    """Move a task note up (-1) or down (+1) in the notes list."""
    if direction not in (-1, +1):
        raise ValueError("direction must be -1 or +1")

    root, task, _parent = _find_root_and_task(repo, task_id)

    idx = next((i for i, n in enumerate(task.notes) if n.id == note_id), None)
    if idx is None:
        return False

    swap_idx = idx + direction
    if swap_idx < 0 or swap_idx >= len(task.notes):
        return False

    # Swap the notes
    task.notes[idx], task.notes[swap_idx] = task.notes[swap_idx], task.notes[idx]

    task.touch(now=now)
    root.touch(now=now)
    repo.upsert_task(root)
    return True


def convert_task_to_subtask(
    repo: TaskRepository,
    task_id: UUID,
    new_parent_id: UUID,
    *,
    now: datetime | None = None,
) -> Task:
    """Convert a task into a subtask of another task.
    
    Args:
        repo: Task repository
        task_id: ID of the task to convert
        new_parent_id: ID of the task that will become the parent
        now: Optional timestamp for updates
        
    Returns:
        The converted task (now a subtask)
        
    Raises:
        ValidationError: If task is already a subtask, has subtasks, or parent not found
    """
    # Find the task to convert
    source_root, task, parent = _find_root_and_task(repo, task_id)
    
    # Validate: task must not already be a subtask
    if parent is not None:
        raise ValidationError("Cannot indent: task is already a subtask")
    
    # Validate: task must not have subtasks (to maintain single level)
    if task.subtasks:
        raise ValidationError("Cannot indent: task has subtasks")
    
    # Find the new parent (make a fresh clone to avoid reference issues)
    new_parent_root, new_parent, new_parent_parent = _find_root_and_task(repo, new_parent_id)
    
    # Validate: new parent must not be a subtask (to maintain single level)
    if new_parent_parent is not None:
        raise ValidationError("Cannot indent: target is a subtask")
    
    # Determine order for the new subtask
    siblings = sorted(new_parent.subtasks, key=lambda t: (t.order, t.created_at))
    next_order = 0
    if siblings:
        next_order = max(t.order for t in siblings) + 1
    
    # Update task order and add to new parent
    task.order = next_order
    task.touch(now=now)
    new_parent.add_subtask(task, now=now)
    new_parent_root.touch(now=now)
    
    # If task and new_parent are in different root trees, 
    # delete the old root and save the new one
    if source_root.id == new_parent_root.id:
        # Same root tree - this shouldn't happen since task is root and parent is root
        # but handle it anyway
        repo.upsert_task(new_parent_root)
    else:
        # Different root trees: delete old root task, save new parent with added subtask
        repo.delete_task(task_id)
        repo.upsert_task(new_parent_root)
    
    return task


def convert_subtask_to_task(
    repo: TaskRepository,
    task_id: UUID,
    *,
    now: datetime | None = None,
) -> Task:
    """Convert a subtask into a root task.
    
    Args:
        repo: Task repository
        task_id: ID of the subtask to convert
        now: Optional timestamp for updates
        
    Returns:
        The converted task (now a root task)
        
    Raises:
        ValidationError: If task is already a root task
    """
    # Find the subtask
    root, task, parent = _find_root_and_task(repo, task_id)
    
    # Validate: task must be a subtask
    if parent is None:
        raise ValidationError("Cannot unindent: task is already a root task")
    
    # Remove task from parent's subtasks
    parent.subtasks = [t for t in parent.subtasks if t.id != task_id]
    parent.touch(now=now)
    root.touch(now=now)
    
    # Save parent (with subtask removed) first
    repo.upsert_task(root)
    
    # Calculate new order: place after parent and all its remaining subtasks
    # Get all roots to determine proper order
    roots = sorted(list(repo.list_tasks()), key=lambda t: (t.order, t.created_at))
    
    # Find parent in roots to get its order
    parent_in_roots = next((r for r in roots if r.id == parent.id), None)
    if parent_in_roots is None:
        # Parent is not a root (shouldn't happen given our validation)
        parent_order = parent.order
    else:
        parent_order = parent_in_roots.order
    
    # Find the next task after parent in the root list
    following_roots = [t for t in roots if t.order > parent_order]
    if following_roots:
        next_root_order = min(t.order for t in following_roots)
        # Check if values are too close (need renormalization)
        if next_root_order - parent_order < 0.001:
            # Trigger renormalization to clean up order values
            normalize_task_order(repo, now=now)
            # Re-fetch roots after normalization
            roots = sorted(list(repo.list_tasks()), key=lambda t: (t.order, t.created_at))
            parent_in_roots = next((r for r in roots if r.id == parent.id), None)
            if parent_in_roots:
                parent_order = parent_in_roots.order
            following_roots = [t for t in roots if t.order > parent_order]
            if following_roots:
                next_root_order = min(t.order for t in following_roots)
                task.order = parent_order + (next_root_order - parent_order) / 2.0
            else:
                task.order = parent_order + 1.0
        else:
            # Use better precision formula: parent + (next - parent) / 2
            task.order = parent_order + (next_root_order - parent_order) / 2.0
    else:
        task.order = parent_order + 1.0
    
    task.touch(now=now)
    
    # Save task as new root
    repo.upsert_task(task)
    
    return task


def normalize_task_order(
    repo: TaskRepository,
    *,
    now: datetime | None = None,
) -> None:
    """Renormalizes task order values to clean sequential integers.
    
    This function resets all task order values to sequential integers (0, 1, 2...)
    based on their current order, preventing precision issues from fractional
    insertions over time. Both root tasks and subtasks are renormalized.
    
    Args:
        repo: Task repository
        now: Optional timestamp for updates
        
    Note:
        This operation updates all tasks in the repository. Use sparingly,
        such as when detecting order values that are too close together.
    """
    roots = sorted(list(repo.list_tasks()), key=lambda t: (t.order, t.created_at))
    
    for i, root in enumerate(roots):
        root_clone = _clone_task(root)
        root_clone.order = float(i)
        
        # Also normalize subtask orders
        sorted_subtasks = sorted(root_clone.subtasks, key=lambda t: (t.order, t.created_at))
        for j, subtask in enumerate(sorted_subtasks):
            subtask.order = float(j)
            subtask.touch(now=now)
        
        root_clone.touch(now=now)
        repo.upsert_task(root_clone)


def archive_completed_tasks(repo: TaskRepository, *, days_threshold: int = 1, now: datetime | None = None) -> int:
    """Archive tasks that have been completed for more than the threshold.
    
    Args:
        repo: Task repository
        days_threshold: Number of days after completion to archive (default: 1)
        now: Current time (for testing)
        
    Returns:
        Number of tasks archived
    """
    current_time = now or utc_now()
    tasks = repo.list_tasks()
    archived_count = 0
    
    def _archive_if_old(task: Task) -> bool:
        """Recursively archive tasks and their subtasks if completed long enough ago.
        
        Returns:
            True if the task was archived
        """
        nonlocal archived_count
        
        # Check subtasks first
        for subtask in task.subtasks[:]:  # Use slice to avoid modifying list during iteration
            _archive_if_old(subtask)
        
        # Archive this task if it's completed and old enough
        if task.status == TaskStatus.DONE and task.completed_at:
            days_completed = (current_time - task.completed_at).total_seconds() / 86400
            if days_completed > days_threshold:
                task.archived = True
                task.touch(now=current_time)
                repo.upsert_task(task)
                archived_count += 1
                return True
        
        return False
    
    for task in tasks:
        _archive_if_old(task)
    
    return archived_count
