"""Tests for SqliteEventRepository."""

from __future__ import annotations

from datetime import date, time
from pathlib import Path

from logui.domain.entities.event import Event
from logui.infrastructure.persistence import SQLiteDatabase
from logui.infrastructure.repositories.events_repo_sqlite import SqliteEventRepository


def test_sqlite_event_repo_empty(tmp_path: Path) -> None:
    """Test repository with no events."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteEventRepository(db)

    assert repo.list_events() == []


def test_sqlite_event_repo_upsert_and_get(tmp_path: Path) -> None:
    """Test upserting and retrieving an event."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteEventRepository(db)

    # Create event
    event = Event.create(
        "Team Meeting",
        day=date(2026, 3, 15),
        start_time=time(10, 0),
        end_time=time(11, 0),
    )

    # Upsert
    repo.upsert_event(event)

    # Get and verify
    loaded = repo.get_event(event.id)
    assert loaded is not None
    assert loaded.id == event.id
    assert loaded.title == "Team Meeting"
    assert loaded.date == date(2026, 3, 15)
    assert loaded.start_time == time(10, 0)
    assert loaded.end_time == time(11, 0)


def test_sqlite_event_repo_upsert_updates(tmp_path: Path) -> None:
    """Test that upsert updates existing event."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteEventRepository(db)

    # Create and upsert event
    event = Event.create("Original Title", day=date(2026, 3, 15))
    repo.upsert_event(event)

    # Update and upsert again
    event.title = "Updated Title"
    event.touch()
    repo.upsert_event(event)

    # Verify update
    loaded = repo.get_event(event.id)
    assert loaded is not None
    assert loaded.title == "Updated Title"

    # Should only have one event
    events = repo.list_events()
    assert len(events) == 1


def test_sqlite_event_repo_delete(tmp_path: Path) -> None:
    """Test deleting an event."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteEventRepository(db)

    # Create and upsert event
    event = Event.create("Test Event", day=date(2026, 3, 15))
    repo.upsert_event(event)

    # Delete
    deleted = repo.delete_event(event.id)
    assert deleted is True

    # Verify deletion
    assert repo.get_event(event.id) is None
    assert repo.list_events() == []

    # Delete again should return False
    deleted_again = repo.delete_event(event.id)
    assert deleted_again is False


def test_sqlite_event_repo_event_with_notes(tmp_path: Path) -> None:
    """Test event with multiple notes."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteEventRepository(db)

    # Create event and add notes
    event = Event.create("Meeting", day=date(2026, 3, 15))
    event.add_note("Remember to bring laptop")
    event.add_note("Prepare slides")

    # Upsert
    repo.upsert_event(event)

    # Load and verify notes
    loaded = repo.get_event(event.id)
    assert loaded is not None
    assert len(loaded.notes) == 2
    assert loaded.notes[0].text == "Remember to bring laptop"
    assert loaded.notes[1].text == "Prepare slides"


def test_sqlite_event_repo_event_notes_deleted_on_delete(tmp_path: Path) -> None:
    """Test that notes are CASCADE deleted with event."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteEventRepository(db)

    # Create event with note
    event = Event.create("Test", day=date(2026, 3, 15))
    event.add_note("Test note")
    repo.upsert_event(event)

    # Verify note exists in database
    conn = db.get_connection()
    cursor = conn.execute("SELECT COUNT(*) FROM event_notes WHERE event_id = ?", (str(event.id),))
    assert cursor.fetchone()[0] == 1

    # Delete event
    repo.delete_event(event.id)

    # Verify note was CASCADE deleted
    cursor = conn.execute("SELECT COUNT(*) FROM event_notes WHERE event_id = ?", (str(event.id),))
    assert cursor.fetchone()[0] == 0


def test_sqlite_event_repo_event_notes_replaced_on_update(tmp_path: Path) -> None:
    """Test that notes are replaced when event is updated."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteEventRepository(db)

    # Create event with one note
    event = Event.create("Test", day=date(2026, 3, 15))
    event.add_note("First note")
    repo.upsert_event(event)

    # Update event with different notes
    event.notes.clear()
    event.add_note("Second note")
    event.add_note("Third note")
    repo.upsert_event(event)

    # Verify notes were replaced
    loaded = repo.get_event(event.id)
    assert loaded is not None
    assert len(loaded.notes) == 2
    assert loaded.notes[0].text == "Second note"
    assert loaded.notes[1].text == "Third note"


def test_sqlite_event_repo_all_day_event(tmp_path: Path) -> None:
    """Test event with no time (all-day event)."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteEventRepository(db)

    # All-day event (no start_time or end_time)
    event = Event.create("Birthday", day=date(2026, 3, 15))
    assert event.start_time is None
    assert event.end_time is None

    repo.upsert_event(event)

    # Load and verify
    loaded = repo.get_event(event.id)
    assert loaded is not None
    assert loaded.start_time is None
    assert loaded.end_time is None


def test_sqlite_event_repo_event_with_repeat(tmp_path: Path) -> None:
    """Test event with recurrence configuration."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteEventRepository(db)

    # Create recurring event
    event = Event.create(
        "Weekly Meeting",
        day=date(2026, 3, 3),
        start_time=time(10, 0),
        repeat={
            "freq": "weekly",
            "interval": 1,
            "weekdays": [0, 2],  # Monday and Wednesday
        },
    )

    repo.upsert_event(event)

    # Load and verify repeat config
    loaded = repo.get_event(event.id)
    assert loaded is not None
    assert loaded.repeat is not None
    assert loaded.repeat["freq"] == "weekly"
    assert loaded.repeat["interval"] == 1
    assert loaded.repeat["weekdays"] == [0, 2]


def test_sqlite_event_repo_list_events_sorted(tmp_path: Path) -> None:
    """Test that list_events returns events sorted by date and time."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteEventRepository(db)

    # Create events in random order
    event1 = Event.create("Event 1", day=date(2026, 3, 15), start_time=time(14, 0))
    event2 = Event.create("Event 2", day=date(2026, 3, 10), start_time=time(10, 0))
    event3 = Event.create("Event 3", day=date(2026, 3, 15), start_time=time(10, 0))

    for event in [event1, event2, event3]:
        repo.upsert_event(event)

    # List should be sorted by date, then time
    events = repo.list_events()
    assert len(events) == 3
    assert events[0].id == event2.id  # 2026-03-10 10:00
    assert events[1].id == event3.id  # 2026-03-15 10:00
    assert events[2].id == event1.id  # 2026-03-15 14:00


def test_sqlite_event_repo_multiple_events(tmp_path: Path) -> None:
    """Test repository with multiple events."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteEventRepository(db)

    # Create multiple events
    events = [
        Event.create("Event 1", day=date(2026, 1, 1)),
        Event.create("Event 2", day=date(2026, 2, 14)),
        Event.create("Event 3", day=date(2026, 3, 15)),
    ]

    for event in events:
        repo.upsert_event(event)

    # Verify all events
    loaded_events = repo.list_events()
    assert len(loaded_events) == 3

    # Verify each event can be retrieved individually
    for event in events:
        loaded = repo.get_event(event.id)
        assert loaded is not None
        assert loaded.id == event.id


def test_sqlite_event_repo_event_with_notification(tmp_path: Path) -> None:
    """Test event with notification settings."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteEventRepository(db)

    # Event with notification
    event = Event.create(
        "Important Meeting",
        day=date(2026, 3, 15),
        start_time=time(10, 0),
        notify=True,
        notify_minutes_before=30,
    )

    repo.upsert_event(event)

    # Verify notification settings
    loaded = repo.get_event(event.id)
    assert loaded is not None
    assert loaded.notify is True
    assert loaded.notify_minutes_before == 30


def test_sqlite_event_repo_get_nonexistent(tmp_path: Path) -> None:
    """Test getting a non-existent event."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteEventRepository(db)

    from uuid import uuid4

    fake_id = uuid4()

    result = repo.get_event(fake_id)
    assert result is None


def test_sqlite_event_repo_event_with_end_day_offset(tmp_path: Path) -> None:
    """Test multi-day event with end_day_offset."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteEventRepository(db)

    # Event spanning 2 days
    event = Event.create(
        "Conference",
        day=date(2026, 3, 15),
        start_time=time(9, 0),
        end_time=time(17, 0),
        end_day_offset=1,  # Ends next day
    )

    repo.upsert_event(event)

    # Verify
    loaded = repo.get_event(event.id)
    assert loaded is not None
    assert loaded.end_day_offset == 1
