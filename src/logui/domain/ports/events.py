from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from logui.domain.entities.event import Event


class EventRepository(ABC):
    @abstractmethod
    def list_events(self) -> list[Event]:
        raise NotImplementedError

    @abstractmethod
    def get_event(self, event_id: UUID) -> Event | None:
        raise NotImplementedError

    @abstractmethod
    def upsert_event(self, event: Event) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete_event(self, event_id: UUID) -> bool:
        raise NotImplementedError
