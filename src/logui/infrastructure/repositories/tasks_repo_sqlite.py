"""SQLite implementation of TaskRepository."""

from __future__ import annotations

import json
import logging
from uuid import UUID

from logui.domain.entities.task import Task, TaskLink, TaskNote
from logui.domain.errors import ValidationError
from logui.domain.ports.tasks import TaskRepository
from logui.infrastructure.persistence import SQLiteDatabase

_log = logging.getLogger(__name__)


class SqliteTaskRepository(TaskRepository):
    """Task repository using SQLite backend.

    Manages tasks with notes, links, and recursive subtasks.
    """

    def __init__(self, db: SQLiteDatabase):
        """Initialize repository.

        Args:
            db: SQLite database manager
        """
        self._db = db

    def list_tasks(self) -> list[Task]:
        """List all root tasks with their subtasks.

        Returns:
            List of root Task instances (parent_id IS NULL)
        """
        try:
            conn = self._db.get_connection()

            # Load all tasks
            cursor = conn.execute("""
                SELECT id, parent_id, task_order, title, status, priority,
                       due_date, link_url, link_text, repeat_data,
                       completed_at, created_at, updated_at
                FROM tasks
                ORDER BY task_order, created_at
            """)

            all_tasks_rows = cursor.fetchall()

            # Load all notes
            notes_cursor = conn.execute("""
                SELECT id, task_id, text, created_at
                FROM task_notes
                ORDER BY created_at
            """)

            # Group notes by task_id
            notes_by_task: dict[str, list[tuple]] = {}
            for note_row in notes_cursor.fetchall():
                task_id = note_row[1]
                if task_id not in notes_by_task:
                    notes_by_task[task_id] = []
                notes_by_task[task_id].append(note_row)

            # Convert rows to Task objects
            tasks_by_id: dict[str, Task] = {}
            for row in all_tasks_rows:
                try:
                    task = self._row_to_task(row, notes_by_task.get(row[0], []))
                    tasks_by_id[row[0]] = task
                except (ValidationError, ValueError) as e:
                    _log.warning("Failed to parse task %s: %s", row[0], e)
                    continue

            # Build hierarchy: attach subtasks to parents
            root_tasks: list[Task] = []
            for task_id, task in tasks_by_id.items():
                parent_id = None
                # Find parent_id from rows
                for row in all_tasks_rows:
                    if row[0] == task_id:
                        parent_id = row[1]
                        break

                if parent_id is None:
                    # Root task
                    root_tasks.append(task)
                else:
                    # Subtask - attach to parent
                    parent = tasks_by_id.get(parent_id)
                    if parent:
                        parent.subtasks.append(task)
                    else:
                        _log.warning(
                            "Orphaned subtask %s (parent %s not found)", task_id, parent_id
                        )
                        # Treat as root if parent not found
                        root_tasks.append(task)

            # Sort root tasks by order
            root_tasks.sort(key=lambda t: (t.order, t.created_at))

            return root_tasks
        except Exception as e:  # noqa: BLE001
            _log.error("Failed to list tasks: %s", e)
            return []

    def get_task(self, task_id: UUID) -> Task | None:
        """Get a specific task by ID.

        Args:
            task_id: Task UUID

        Returns:
            Task instance with subtasks, or None if not found
        """
        try:
            # Load all tasks and build hierarchy (simpler than complex query)
            all_tasks = self.list_tasks()

            # Find task recursively
            def find_task(tasks: list[Task], target_id: UUID) -> Task | None:
                for task in tasks:
                    if task.id == target_id:
                        return task
                    # Check subtasks recursively
                    found = find_task(task.subtasks, target_id)
                    if found:
                        return found
                return None

            return find_task(all_tasks, task_id)
        except Exception as e:  # noqa: BLE001
            _log.error("Failed to get task %s: %s", task_id, e)
            return None

    def upsert_task(self, task: Task) -> None:
        """Insert or update a task with its subtasks.

        Args:
            task: Task instance to save
        """
        with self._db.transaction() as conn:
            self._upsert_task_recursive(conn, task, parent_id=None)

        _log.debug("Task %s upserted successfully", task.id)

    def delete_task(self, task_id: UUID) -> bool:
        """Delete a task and its subtasks (CASCADE).

        Args:
            task_id: Task UUID

        Returns:
            True if task was deleted, False if not found
        """
        with self._db.transaction() as conn:
            cursor = conn.execute(
                """
                DELETE FROM tasks WHERE id = ?
            """,
                (str(task_id),),
            )
            deleted = cursor.rowcount > 0

        if deleted:
            _log.debug("Task %s deleted", task_id)

        return deleted

    def _upsert_task_recursive(self, conn, task: Task, parent_id: UUID | None) -> None:
        """Recursively upsert task and its subtasks.

        Args:
            conn: Database connection
            task: Task to upsert
            parent_id: Parent task UUID, or None for root tasks
        """
        # Delete old notes
        conn.execute(
            """
            DELETE FROM task_notes WHERE task_id = ?
        """,
            (str(task.id),),
        )

        # Prepare data
        repeat_data = json.dumps(task.repeat) if task.repeat else None

        # Upsert task
        conn.execute(
            """
            INSERT OR REPLACE INTO tasks (
                id, parent_id, task_order, title, status, priority,
                due_date, link_url, link_text, repeat_data,
                completed_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                str(task.id),
                str(parent_id) if parent_id else None,
                task.order,
                task.title,
                task.status.value,
                1 if task.priority else 0,
                task.due_date.isoformat() if task.due_date else None,
                task.link.url if task.link else None,
                task.link.text if task.link else None,
                repeat_data,
                self._format_datetime(task.completed_at) if task.completed_at else None,
                self._format_datetime(task.created_at),
                self._format_datetime(task.updated_at),
            ),
        )

        # Insert notes
        for note in task.notes:
            conn.execute(
                """
                INSERT INTO task_notes (id, task_id, text, created_at)
                VALUES (?, ?, ?, ?)
            """,
                (
                    str(note.id),
                    str(task.id),
                    note.text,
                    self._format_datetime(note.created_at),
                ),
            )

        # Recursively upsert subtasks
        for subtask in task.subtasks:
            self._upsert_task_recursive(conn, subtask, parent_id=task.id)

    def _row_to_task(self, task_row: tuple, notes_rows: list[tuple]) -> Task:
        """Convert database row to Task instance.

        Args:
            task_row: Task table row
            notes_rows: List of task_notes table rows

        Returns:
            Task instance (without subtasks - those are attached later)
        """
        # Parse link
        link = None
        if task_row[7]:  # link_url
            try:
                link = TaskLink.create(task_row[7], text=task_row[8])
            except ValidationError as e:
                _log.warning("Failed to parse task link: %s", e)

        # Parse repeat_data
        repeat = None
        if task_row[9]:  # repeat_data
            try:
                repeat = json.loads(task_row[9])
            except json.JSONDecodeError as e:
                _log.warning("Failed to parse repeat_data for task %s: %s", task_row[0], e)

        # Parse notes
        notes = []
        for note_row in notes_rows:
            try:
                note = TaskNote.from_dict(
                    {
                        "id": note_row[0],
                        "text": note_row[2],
                        "created_at": note_row[3],
                    }
                )
                notes.append(note)
            except (ValidationError, ValueError) as e:
                _log.warning("Failed to parse task note %s: %s", note_row[0], e)
                continue

        # Build task dict
        task_dict = {
            "id": task_row[0],
            "order": task_row[2],
            "title": task_row[3],
            "status": task_row[4],
            "priority": bool(task_row[5]),
            "due_date": task_row[6],
            "link": link.to_dict() if link else None,
            "repeat": repeat,
            "notes": [n.to_dict() for n in notes],
            "subtasks": [],  # Will be populated by list_tasks
            "completed_at": task_row[10],
            "created_at": task_row[11],
            "updated_at": task_row[12],
        }

        return Task.from_dict(task_dict)

    @staticmethod
    def _format_datetime(dt) -> str:
        """Format datetime to ISO string with Z suffix."""
        return dt.isoformat().replace("+00:00", "Z")
