"""Tests for event reordering after edits."""

from __future__ import annotations

from datetime import date, time
from pathlib import Path

from logui.infrastructure.persistence.sqlite_database import SQLiteDatabase
from logui.infrastructure.repositories.events_repo_sqlite import SqliteEventRepository
from logui.usecases.events import (
    CreateEventInput,
    UpdateEventPatch,
    create_event,
    update_event,
)


def test_update_event_time_changes_order(tmp_path: Path) -> None:
    """Test that updating an event's time causes it to be reordered correctly."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteEventRepository(db)
    day = date(2025, 12, 25)

    # Create three events in order: 9:00, 11:00, 15:00
    event_9am = create_event(
        repo,
        CreateEventInput(
            title="Morning meeting",
            day=day,
            start_time=time(9, 0),
            end_time=time(10, 0),
        ),
    )

    event_11am = create_event(
        repo,
        CreateEventInput(
            title="Late morning",
            day=day,
            start_time=time(11, 0),
            end_time=time(12, 0),
        ),
    )

    event_3pm = create_event(
        repo,
        CreateEventInput(
            title="Afternoon",
            day=day,
            start_time=time(15, 0),
            end_time=time(16, 0),
        ),
    )

    # Verify initial order
    all_events = sorted(
        repo.list_events(),
        key=lambda e: (
            e.date,
            0 if e.start_time is None else 1,
            e.start_time or time(0, 0),
            str(e.id),
        ),
    )
    assert [e.id for e in all_events] == [event_9am.id, event_11am.id, event_3pm.id]

    # Update the 3pm event to be at 10:00 (should move it between 9am and 11am)
    updated = update_event(
        repo,
        event_3pm.id,
        UpdateEventPatch(start_time=time(10, 0), end_time=time(11, 0)),
    )

    # Verify it was updated
    assert updated.start_time == time(10, 0)
    assert updated.title == "Afternoon"

    # Verify new order: should now be 9am, 10am (was 3pm), 11am
    all_events = sorted(
        repo.list_events(),
        key=lambda e: (
            e.date,
            0 if e.start_time is None else 1,
            e.start_time or time(0, 0),
            str(e.id),
        ),
    )
    assert [e.id for e in all_events] == [event_9am.id, event_3pm.id, event_11am.id]


def test_update_event_date_changes_order(tmp_path: Path) -> None:
    """Test that updating an event's date causes it to be reordered correctly."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteEventRepository(db)

    # Create events on different days
    event_dec_25 = create_event(
        repo,
        CreateEventInput(
            title="Christmas",
            day=date(2025, 12, 25),
            start_time=time(10, 0),
        ),
    )

    event_dec_26 = create_event(
        repo,
        CreateEventInput(
            title="Boxing Day",
            day=date(2025, 12, 26),
            start_time=time(10, 0),
        ),
    )

    event_dec_27 = create_event(
        repo,
        CreateEventInput(
            title="Day after Boxing Day",
            day=date(2025, 12, 27),
            start_time=time(10, 0),
        ),
    )

    # Verify initial order (by date)
    all_events = sorted(
        repo.list_events(),
        key=lambda e: (
            e.date,
            0 if e.start_time is None else 1,
            e.start_time or time(0, 0),
            str(e.id),
        ),
    )
    assert [e.id for e in all_events] == [event_dec_25.id, event_dec_26.id, event_dec_27.id]

    # Update Dec 27 event to be on Dec 24 (should move to the beginning)
    updated = update_event(
        repo,
        event_dec_27.id,
        UpdateEventPatch(day=date(2025, 12, 24)),
    )

    assert updated.date == date(2025, 12, 24)

    # Verify new order: should now be Dec 24 (was 27), 25, 26
    all_events = sorted(
        repo.list_events(),
        key=lambda e: (
            e.date,
            0 if e.start_time is None else 1,
            e.start_time or time(0, 0),
            str(e.id),
        ),
    )
    assert [e.id for e in all_events] == [event_dec_27.id, event_dec_25.id, event_dec_26.id]


def test_update_all_day_to_timed_changes_order(tmp_path: Path) -> None:
    """Test that converting an all-day event to timed changes its position."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteEventRepository(db)
    day = date(2025, 12, 25)

    # Create all-day event and timed event
    all_day = create_event(
        repo,
        CreateEventInput(
            title="All day event",
            day=day,
            start_time=None,  # All-day
        ),
    )

    morning = create_event(
        repo,
        CreateEventInput(
            title="Morning event",
            day=day,
            start_time=time(9, 0),
        ),
    )

    # All-day events come first
    all_events = sorted(
        repo.list_events(),
        key=lambda e: (
            e.date,
            0 if e.start_time is None else 1,
            e.start_time or time(0, 0),
            str(e.id),
        ),
    )
    assert [e.id for e in all_events] == [all_day.id, morning.id]

    # Convert all-day to timed at 15:00
    updated = update_event(
        repo,
        all_day.id,
        UpdateEventPatch(start_time=time(15, 0)),
    )

    assert updated.start_time == time(15, 0)

    # Now the morning event should come first
    all_events = sorted(
        repo.list_events(),
        key=lambda e: (
            e.date,
            0 if e.start_time is None else 1,
            e.start_time or time(0, 0),
            str(e.id),
        ),
    )
    assert [e.id for e in all_events] == [morning.id, all_day.id]


def test_update_timed_to_all_day_changes_order(tmp_path: Path) -> None:
    """Test that converting a timed event to all-day changes its position."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteEventRepository(db)
    day = date(2025, 12, 25)

    # Create timed events
    morning = create_event(
        repo,
        CreateEventInput(
            title="Morning event",
            day=day,
            start_time=time(9, 0),
        ),
    )

    afternoon = create_event(
        repo,
        CreateEventInput(
            title="Afternoon event",
            day=day,
            start_time=time(15, 0),
        ),
    )

    # Initially ordered by time
    all_events = sorted(
        repo.list_events(),
        key=lambda e: (
            e.date,
            0 if e.start_time is None else 1,
            e.start_time or time(0, 0),
            str(e.id),
        ),
    )
    assert [e.id for e in all_events] == [morning.id, afternoon.id]

    # Convert afternoon event to all-day
    updated = update_event(
        repo,
        afternoon.id,
        UpdateEventPatch(start_time=None),
    )

    assert updated.start_time is None

    # All-day events come first, so afternoon should now be first
    all_events = sorted(
        repo.list_events(),
        key=lambda e: (
            e.date,
            0 if e.start_time is None else 1,
            e.start_time or time(0, 0),
            str(e.id),
        ),
    )
    assert [e.id for e in all_events] == [afternoon.id, morning.id]
