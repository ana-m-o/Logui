from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from logui.domain.ports.journal import JournalRepository
from logui.infrastructure.repositories.json_store import JsonStore


class JsonJournalRepository(JournalRepository):
    def __init__(self, path: Path):
        self._store = JsonStore(path)

    def _load_entries(self) -> dict[str, Any]:
        doc = self._store.read()
        if not doc:
            return {}
        return doc.get("entries") or {}

    def list_entry_days(self) -> list[date]:
        entries = self._load_entries()
        days: list[date] = []
        for k, v in entries.items():
            if not v:
                continue
            try:
                days.append(date.fromisoformat(str(k)))
            except Exception:  # noqa: BLE001
                continue
        days.sort(reverse=True)
        return days

    def get_entry(self, day: date) -> str | None:
        entries = self._load_entries()
        item = entries.get(day.isoformat())
        if not item:
            return None
        return item.get("text")

    def set_entry(self, day: date, text: str) -> None:
        cleaned = text or ""
        entries = self._load_entries()
        entries[day.isoformat()] = {
            "text": cleaned,
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        doc: dict[str, Any] = {"schema_version": 1, "entries": entries}
        self._store.write_atomic(doc)

    def delete_entry(self, day: date) -> bool:
        entries = self._load_entries()
        key = day.isoformat()
        existed = key in entries
        if existed:
            del entries[key]
        doc: dict[str, Any] = {"schema_version": 1, "entries": entries}
        self._store.write_atomic(doc)
        return existed
