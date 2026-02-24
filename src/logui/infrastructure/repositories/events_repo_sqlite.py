"""SQLite implementation of EventRepository."""

from __future__ import annotations

import json
import logging
from datetime import date, time
from uuid import UUID

from logui.domain.entities.event import Event, EventNote
from logui.domain.errors import ValidationError
from logui.domain.ports.events import EventRepository
from logui.infrastructure.persistence import SQLiteDatabase

_log = logging.getLogger(__name__)


class SqliteEventRepository(EventRepository):
    """Event repository using SQLite backend.
    
    Manages events and their associated notes in separate tables.
    """

    def __init__(self, db: SQLiteDatabase):
        """Initialize repository.
        
        Args:
            db: SQLite database manager
        """
        self._db = db

    def list_events(self) -> list[Event]:
        """List all events with their notes.
        
        Returns:
            List of Event instances
        """
        try:
            conn = self._db.get_connection()
            
            # Load all events
            cursor = conn.execute("""
                SELECT id, title, date, start_time, end_time, end_day_offset,
                       notify, notify_minutes_before, repeat_json,
                       created_at, updated_at
                FROM events
                ORDER BY date, start_time
            """)
            
            events_data = cursor.fetchall()
            
            # Load all notes
            notes_cursor = conn.execute("""
                SELECT id, event_id, text, created_at
                FROM event_notes
                ORDER BY created_at
            """)
            
            # Group notes by event_id
            notes_by_event: dict[str, list[tuple]] = {}
            for note_row in notes_cursor.fetchall():
                event_id = note_row[1]
                if event_id not in notes_by_event:
                    notes_by_event[event_id] = []
                notes_by_event[event_id].append(note_row)
            
            # Reconstruct Event objects
            events: list[Event] = []
            for row in events_data:
                try:
                    event = self._row_to_event(row, notes_by_event.get(row[0], []))
                    events.append(event)
                except (ValidationError, ValueError) as e:
                    _log.warning("Failed to parse event %s: %s", row[0], e)
                    continue
            
            return events
        except Exception as e:  # noqa: BLE001
            _log.error("Failed to list events: %s", e)
            return []

    def get_event(self, event_id: UUID) -> Event | None:
        """Get a specific event by ID.
        
        Args:
            event_id: Event UUID
        
        Returns:
            Event instance, or None if not found
        """
        try:
            conn = self._db.get_connection()
            
            # Load event
            cursor = conn.execute("""
                SELECT id, title, date, start_time, end_time, end_day_offset,
                       notify, notify_minutes_before, repeat_json,
                       created_at, updated_at
                FROM events
                WHERE id = ?
            """, (str(event_id),))
            
            event_row = cursor.fetchone()
            if not event_row:
                return None
            
            # Load notes for this event
            notes_cursor = conn.execute("""
                SELECT id, event_id, text, created_at
                FROM event_notes
                WHERE event_id = ?
                ORDER BY created_at
            """, (str(event_id),))
            
            notes_rows = notes_cursor.fetchall()
            
            return self._row_to_event(event_row, notes_rows)
        except (ValidationError, ValueError) as e:
            _log.error("Failed to parse event %s: %s", event_id, e)
            return None
        except Exception as e:  # noqa: BLE001
            _log.error("Failed to get event %s: %s", event_id, e)
            return None

    def upsert_event(self, event: Event) -> None:
        """Insert or update an event.
        
        Args:
            event: Event instance to save
        """
        with self._db.transaction() as conn:
            # Delete old notes (simpler than diffing)
            conn.execute("""
                DELETE FROM event_notes WHERE event_id = ?
            """, (str(event.id),))
            
            # Upsert event
            repeat_json = json.dumps(event.repeat) if event.repeat else None
            
            conn.execute("""
                INSERT OR REPLACE INTO events (
                    id, title, date, start_time, end_time, end_day_offset,
                    notify, notify_minutes_before, repeat_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(event.id),
                event.title,
                event.date.isoformat(),
                event.start_time.isoformat(timespec="minutes") if event.start_time else None,
                event.end_time.isoformat(timespec="minutes") if event.end_time else None,
                event.end_day_offset,
                1 if event.notify else 0,
                event.notify_minutes_before,
                repeat_json,
                self._format_datetime(event.created_at),
                self._format_datetime(event.updated_at),
            ))
            
            # Insert new notes
            for note in event.notes:
                conn.execute("""
                    INSERT INTO event_notes (id, event_id, text, created_at)
                    VALUES (?, ?, ?, ?)
                """, (
                    str(note.id),
                    str(event.id),
                    note.text,
                    self._format_datetime(note.created_at),
                ))
        
        _log.debug("Event %s upserted successfully", event.id)

    def delete_event(self, event_id: UUID) -> bool:
        """Delete an event.
        
        Args:
            event_id: Event UUID
        
        Returns:
            True if event was deleted, False if not found
        """
        with self._db.transaction() as conn:
            cursor = conn.execute("""
                DELETE FROM events WHERE id = ?
            """, (str(event_id),))
            deleted = cursor.rowcount > 0
        
        if deleted:
            _log.debug("Event %s deleted", event_id)
        
        return deleted

    def _row_to_event(self, event_row: tuple, notes_rows: list[tuple]) -> Event:
        """Convert database rows to Event instance.
        
        Args:
            event_row: Event table row
            notes_rows: List of event_notes table rows
        
        Returns:
            Event instance
        """
        # Parse repeat_json
        repeat = None
        if event_row[8]:  # repeat_json
            try:
                repeat = json.loads(event_row[8])
            except json.JSONDecodeError as e:
                _log.warning("Failed to parse repeat_json for event %s: %s", event_row[0], e)
        
        # Parse notes
        notes = []
        for note_row in notes_rows:
            try:
                note = EventNote.from_dict({
                    "id": note_row[0],
                    "text": note_row[2],
                    "created_at": note_row[3],
                })
                notes.append(note)
            except (ValidationError, ValueError) as e:
                _log.warning("Failed to parse event note %s: %s", note_row[0], e)
                continue
        
        # Build event dict
        event_dict = {
            "id": event_row[0],
            "title": event_row[1],
            "date": event_row[2],
            "start_time": event_row[3],
            "end_time": event_row[4],
            "end_day_offset": event_row[5],
            "notify": bool(event_row[6]),
            "notify_minutes_before": event_row[7],
            "repeat": repeat,
            "notes": [n.to_dict() for n in notes],
            "created_at": event_row[9],
            "updated_at": event_row[10],
        }
        
        return Event.from_dict(event_dict)

    @staticmethod
    def _format_datetime(dt) -> str:
        """Format datetime to ISO string with Z suffix."""
        return dt.isoformat().replace("+00:00", "Z")
