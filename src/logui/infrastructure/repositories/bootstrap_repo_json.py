from __future__ import annotations

from pathlib import Path

from logui.domain.entities.bootstrap import BootstrapConfig
from logui.infrastructure.repositories.json_store import JsonStore


class JsonBootstrapRepository:
    """Stores BootstrapConfig as JSON.

    This file is intentionally separate from the full app config.
    """

    def __init__(self, path: Path):
        self._store = JsonStore(path)

    def load(self) -> BootstrapConfig:
        doc = self._store.read()
        if not doc:
            return BootstrapConfig.default()
        try:
            return BootstrapConfig.from_dict(doc)
        except Exception:  # noqa: BLE001
            return BootstrapConfig.default()

    def save(self, config: BootstrapConfig) -> None:
        self._store.write_atomic(config.to_dict())
