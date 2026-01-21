from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from logui.domain.entities.task import Task
from logui.domain.ports.tasks import TaskRepository
from logui.infrastructure.repositories.json_store import JsonStore


class JsonTaskRepository(TaskRepository):
    def __init__(self, path: Path):
        self._store = JsonStore(path)

    def list_tasks(self) -> list[Task]:
        doc = self._store.read()
        if not doc:
            return []
        raw_tasks: list[dict[str, Any]] = doc.get("tasks") or []

        tasks = [Task.from_dict(t) for t in raw_tasks]
        return sorted(tasks, key=lambda t: (t.order, t.created_at))

    def get_task(self, task_id: UUID) -> Task | None:
        for task in self.list_tasks():
            if task.id == task_id:
                return task
        return None

    def upsert_task(self, task: Task) -> None:
        existing = self.list_tasks()
        by_id: dict[UUID, Task] = {t.id: t for t in existing}
        by_id[task.id] = task
        ordered = sorted(by_id.values(), key=lambda t: (t.order, t.created_at))
        doc: dict[str, Any] = {
            "schema_version": 1,
            "tasks": [t.to_dict() for t in ordered],
        }
        self._store.write_atomic(doc)

    def delete_task(self, task_id: UUID) -> bool:
        existing = self.list_tasks()
        kept = [t for t in existing if t.id != task_id]
        deleted = len(kept) != len(existing)
        kept_sorted = sorted(kept, key=lambda t: (t.order, t.created_at))
        doc: dict[str, Any] = {
            "schema_version": 1,
            "tasks": [t.to_dict() for t in kept_sorted],
        }
        self._store.write_atomic(doc)
        return deleted
