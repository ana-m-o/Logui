from __future__ import annotations

from pathlib import Path

from logui.domain.entities.config import AppConfig
from logui.domain.ports.config import ConfigRepository
from logui.infrastructure.repositories.json_store import JsonStore


class JsonConfigRepository(ConfigRepository):
    def __init__(self, path: Path):
        self._store = JsonStore(path)

    def load(self) -> AppConfig:
        doc = self._store.read()
        if not doc:
            return AppConfig.default()
        try:
            return AppConfig.from_dict(doc)
        except Exception:  # noqa: BLE001
            # Best-effort recovery: fall back to defaults.
            return AppConfig.default()

    def save(self, config: AppConfig) -> None:
        self._store.write_atomic(config.to_dict())
