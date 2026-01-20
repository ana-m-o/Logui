from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BootstrapConfig:
    """Bootstrap configuration.

    This config lives in the default directory and only contains the information
    needed to locate the real data directory (and therefore the full config).
    """

    schema_version: int = 1
    data_directory: str | None = None

    @staticmethod
    def default() -> "BootstrapConfig":
        return BootstrapConfig()

    @staticmethod
    def from_dict(data: dict[str, Any] | None) -> "BootstrapConfig":
        data = data or {}
        schema_version = int(data.get("schema_version", 1) or 1)
        raw = data.get("data_directory")
        data_directory = str(raw).strip() if raw is not None else ""
        if not data_directory:
            data_directory = None
        return BootstrapConfig(schema_version=schema_version, data_directory=data_directory)

    def to_dict(self) -> dict[str, Any]:
        doc: dict[str, Any] = {"schema_version": int(self.schema_version)}
        if self.data_directory:
            doc["data_directory"] = str(self.data_directory)
        return doc
