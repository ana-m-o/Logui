"""SQLite implementation of ConfigRepository."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from logui.domain.entities.config import AppConfig
from logui.domain.ports.config import ConfigRepository
from logui.infrastructure.persistence import SQLiteDatabase

_log = logging.getLogger(__name__)


class SqliteConfigRepository(ConfigRepository):
    """Config repository using SQLite backend.

    Stores AppConfig as a JSON blob in a singleton table row.
    """

    def __init__(self, db: SQLiteDatabase):
        """Initialize repository.

        Args:
            db: SQLite database manager
        """
        self._db = db

    def load(self) -> AppConfig:
        """Load application configuration.

        Returns:
            AppConfig instance, or default config if not found
        """
        try:
            conn = self._db.get_connection()
            cursor = conn.execute("SELECT config_json FROM config WHERE id = 1")
            row = cursor.fetchone()

            if not row:
                _log.debug("No config found in database, returning default")
                return AppConfig.default()

            config_dict = json.loads(row[0])
            return AppConfig.from_dict(config_dict)
        except json.JSONDecodeError as e:
            _log.error("Failed to parse config JSON: %s", e)
            return AppConfig.default()
        except Exception as e:  # noqa: BLE001
            _log.error("Failed to load config: %s", e)
            return AppConfig.default()

    def save(self, config: AppConfig) -> None:
        """Save application configuration.

        Args:
            config: AppConfig to persist
        """
        config_json = json.dumps(config.to_dict(), ensure_ascii=False, sort_keys=False)
        updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO config (id, config_json, updated_at)
                VALUES (1, ?, ?)
            """,
                (config_json, updated_at),
            )

        _log.debug("Config saved successfully")
