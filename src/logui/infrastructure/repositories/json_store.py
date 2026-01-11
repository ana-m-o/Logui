from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class JsonStore:
    path: Path

    def read(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        raw = self.path.read_text(encoding="utf-8")
        return json.loads(raw)

    def write_atomic(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = json.dumps(data, ensure_ascii=False, indent=3, sort_keys=False) + "\n"
        tmp_path.write_text(payload, encoding="utf-8")
        os.replace(tmp_path, self.path)
