from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from logui.domain.entities.task import Task


class TaskRepository(ABC):
    @abstractmethod
    def list_tasks(self) -> list[Task]:
        raise NotImplementedError

    @abstractmethod
    def get_task(self, task_id: UUID) -> Task | None:
        raise NotImplementedError

    @abstractmethod
    def upsert_task(self, task: Task) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete_task(self, task_id: UUID) -> bool:
        raise NotImplementedError
