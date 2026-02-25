"""Test recurring events in use cases."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from logui.infrastructure.persistence.sqlite_database import SQLiteDatabase
from logui.infrastructure.repositories.events_repo_sqlite import SqliteEventRepository
from logui.usecases import CreateEventInput, create_event, cycle_event_repeat, list_events_for_date


def test_list_events_for_date_includes_recurring_occurrences(tmp_path: Path) -> None:
    """Recurring events should appear when listing events for their occurrence dates."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteEventRepository(db)

    # Create a daily recurring event starting Jan 15
    create_event(
        repo,
        CreateEventInput(
            title="Daily standup",
            day=date(2026, 1, 15),
            repeat={"freq": "daily", "interval": 1},
        ),
    )

    # Create a non-recurring event on Jan 16
    create_event(
        repo,
        CreateEventInput(
            title="One-time meeting",
            day=date(2026, 1, 16),
        ),
    )

    # List events for Jan 15: should include only the daily standup
    events_jan15 = list_events_for_date(repo, date(2026, 1, 15))
    assert len(events_jan15) == 1
    assert events_jan15[0].title == "Daily standup"

    # List events for Jan 16: should include both (recurring + one-time)
    events_jan16 = list_events_for_date(repo, date(2026, 1, 16))
    assert len(events_jan16) == 2
    titles = {e.title for e in events_jan16}
    assert titles == {"Daily standup", "One-time meeting"}

    # List events for Jan 20: should include only the recurring event
    events_jan20 = list_events_for_date(repo, date(2026, 1, 20))
    assert len(events_jan20) == 1
    assert events_jan20[0].title == "Daily standup"


def test_list_events_for_date_weekly_recurring(tmp_path: Path) -> None:
    """Weekly recurring events appear only on correct weekday."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteEventRepository(db)

    # Create weekly event starting Jan 15 (Thursday)
    create_event(
        repo,
        CreateEventInput(
            title="Weekly review",
            day=date(2026, 1, 15),
            repeat={"freq": "weekly", "interval": 1},
        ),
    )

    # Jan 15 (Thu) - should appear
    events = list_events_for_date(repo, date(2026, 1, 15))
    assert len(events) == 1

    # Jan 16 (Fri) - should NOT appear
    events = list_events_for_date(repo, date(2026, 1, 16))
    assert len(events) == 0

    # Jan 22 (next Thu) - should appear
    events = list_events_for_date(repo, date(2026, 1, 22))
    assert len(events) == 1

    # Jan 29 (next next Thu) - should appear
    events = list_events_for_date(repo, date(2026, 1, 29))
    assert len(events) == 1


def test_list_events_for_date_monthly_recurring(tmp_path: Path) -> None:
    """Monthly recurring events appear on same day of month."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteEventRepository(db)

    # Create monthly event starting Jan 15
    create_event(
        repo,
        CreateEventInput(
            title="Monthly report",
            day=date(2026, 1, 15),
            repeat={"freq": "monthly", "interval": 1},
        ),
    )

    # Jan 15 - should appear
    events = list_events_for_date(repo, date(2026, 1, 15))
    assert len(events) == 1

    # Jan 16 - should NOT appear
    events = list_events_for_date(repo, date(2026, 1, 16))
    assert len(events) == 0

    # Feb 15 - should appear
    events = list_events_for_date(repo, date(2026, 2, 15))
    assert len(events) == 1

    # Mar 15 - should appear
    events = list_events_for_date(repo, date(2026, 3, 15))
    assert len(events) == 1


def test_list_events_for_date_respects_until(tmp_path: Path) -> None:
    """Recurring events with 'until' stop after that date."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteEventRepository(db)

    # Create daily event with until Jan 20
    create_event(
        repo,
        CreateEventInput(
            title="Limited daily",
            day=date(2026, 1, 15),
            repeat={"freq": "daily", "interval": 1, "until": "2026-01-20"},
        ),
    )

    # Jan 20 - should still appear
    events = list_events_for_date(repo, date(2026, 1, 20))
    assert len(events) == 1

    # Jan 21 - should NOT appear (after until)
    events = list_events_for_date(repo, date(2026, 1, 21))
    assert len(events) == 0


def test_cycle_event_repeat_updates_freq(tmp_path: Path) -> None:
    """Cycling repeat updates the frequency correctly."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteEventRepository(db)

    ev = create_event(
        repo,
        CreateEventInput(
            title="Test event",
            day=date(2026, 1, 15),
        ),
    )

    # Initial: no repeat
    assert ev.repeat is None or ev.repeat.get("freq") == "none"

    # Cycle to daily
    ev = cycle_event_repeat(repo, ev.id)
    assert ev.repeat == {"freq": "daily"}

    # Cycle to weekly
    ev = cycle_event_repeat(repo, ev.id)
    assert ev.repeat == {"freq": "weekly"}

    # Cycle to monthly
    ev = cycle_event_repeat(repo, ev.id)
    assert ev.repeat == {"freq": "monthly"}

    # Cycle back to none
    ev = cycle_event_repeat(repo, ev.id)
    assert ev.repeat == {"freq": "none"}
