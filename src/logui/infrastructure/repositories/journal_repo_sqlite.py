"""SQLite implementation of JournalRepository."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from logui.domain.ports.journal import JournalRepository
from logui.infrastructure.persistence import SQLiteDatabase

_log = logging.getLogger(__name__)


class SqliteJournalRepository(JournalRepository):
    """Journal repository using SQLite backend.
    
    Stores journal entries with date as primary key.
    """

    def __init__(self, db: SQLiteDatabase):
        """Initialize repository.
        
        Args:
            db: SQLite database manager
        """
        self._db = db

    def list_entry_days(self) -> list[date]:
        """List all days with journal entries.
        
        Returns:
            List of dates with entries, sorted descending (newest first)
        """
        try:
            conn = self._db.get_connection()
            cursor = conn.execute("""
                SELECT date FROM journal_entries
                WHERE text IS NOT NULL AND text != ''
                ORDER BY date DESC
            """)
            
            days: list[date] = []
            for row in cursor.fetchall():
                try:
                    days.append(date.fromisoformat(row[0]))
                except (ValueError, TypeError) as e:
                    _log.warning("Invalid date in journal_entries: %s (%s)", row[0], e)
                    continue
            
            return days
        except Exception as e:  # noqa: BLE001
            _log.error("Failed to list journal entry days: %s", e)
            return []

    def get_entry(self, day: date) -> str | None:
        """Get journal entry for a specific day.
        
        Args:
            day: Date to get entry for
        
        Returns:
            Entry text, or None if no entry exists
        """
        try:
            conn = self._db.get_connection()
            cursor = conn.execute("""
                SELECT text FROM journal_entries
                WHERE date = ?
            """, (day.isoformat(),))
            
            row = cursor.fetchone()
            return row[0] if row else None
        except Exception as e:  # noqa: BLE001
            _log.error("Failed to get journal entry for %s: %s", day, e)
            return None

    def set_entry(self, day: date, text: str) -> None:
        """Set journal entry for a specific day.
        
        Args:
            day: Date to set entry for
            text: Entry text (can be empty string)
        """
        cleaned = text or ""
        updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        with self._db.transaction() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO journal_entries (date, text, updated_at)
                VALUES (?, ?, ?)
            """, (day.isoformat(), cleaned, updated_at))
        
        _log.debug("Journal entry saved for %s", day)

    def delete_entry(self, day: date) -> bool:
        """Delete journal entry for a specific day.
        
        Args:
            day: Date to delete entry for
        
        Returns:
            True if entry was deleted, False if no entry existed
        """
        with self._db.transaction() as conn:
            cursor = conn.execute("""
                DELETE FROM journal_entries WHERE date = ?
            """, (day.isoformat(),))
            deleted = cursor.rowcount > 0
        
        if deleted:
            _log.debug("Journal entry deleted for %s", day)
        
        return deleted
