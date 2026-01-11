from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from logui.domain.entities.event import Event
from logui.domain.ports.events import EventRepository
from logui.infrastructure.repositories.json_store import JsonStore


class JsonEventRepository(EventRepository):
    def __init__(self, path: Path):
        self._store = JsonStore(path)

    def list_events(self) -> list[Event]:
        doc = self._store.read()
        if not doc:
            return []
        events = doc.get("events") or []
        return [Event.from_dict(e) for e in events]

    def get_event(self, event_id: UUID) -> Event | None:
        for ev in self.list_events():
            if ev.id == event_id:
                return ev
        return None

    def upsert_event(self, event: Event) -> None:
        existing = self.list_events()
        by_id: dict[UUID, Event] = {e.id: e for e in existing}
        by_id[event.id] = event
        doc: dict[str, Any] = {
            "schema_version": 1,
            "events": [e.to_dict() for e in by_id.values()],
        }
        self._store.write_atomic(doc)

    def delete_event(self, event_id: UUID) -> bool:
        existing = self.list_events()
        kept = [e for e in existing if e.id != event_id]
        deleted = len(kept) != len(existing)
        doc: dict[str, Any] = {
            "schema_version": 1,
            "events": [e.to_dict() for e in kept],
        }
        self._store.write_atomic(doc)
        return deleted
