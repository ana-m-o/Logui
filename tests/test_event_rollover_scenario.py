"""Test to simulate day rollover with events from previous day."""

from datetime import date, time

from logui.infrastructure.persistence.sqlite_database import SQLiteDatabase
from logui.infrastructure.repositories.events_repo_sqlite import SqliteEventRepository
from logui.ui.event_temporal import is_visible_in_events_pane
from logui.usecases.events import CreateEventInput, create_event, process_recurring_events


def test_non_recurring_events_disappear_after_rollover(tmp_path):
    """Simulate day rollover - non-recurring events from yesterday should disappear."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteEventRepository(db)

    # Day 1: Create events on Jan 23
    yesterday = date(2026, 1, 23)
    today = date(2026, 1, 24)

    # Create a regular event on Jan 23
    event1 = create_event(
        repo,
        CreateEventInput(
            title="Meeting on 23rd",
            day=yesterday,
            start_time=time(10, 0),
            notify=False,
        ),
    )

    # Create a recurring event on Jan 23
    event2 = create_event(
        repo,
        CreateEventInput(
            title="Daily standup",
            day=yesterday,
            start_time=time(9, 0),
            notify=False,
            repeat={"freq": "daily"},
        ),
    )

    # Before rollover: both should be visible on their day
    all_events_day1 = [
        ev for ev in repo.list_events() if is_visible_in_events_pane(ev, today=yesterday)
    ]
    assert len(all_events_day1) == 2

    # Simulate day rollover to Jan 24
    # 1. Process recurring events (clone them)
    new_events = process_recurring_events(repo, today=today)
    assert len(new_events) == 1  # Only the recurring one should clone
    assert new_events[0].title == "Daily standup"
    assert new_events[0].date == today

    # 2. Check visibility after rollover
    all_events_day2 = [
        ev for ev in repo.list_events() if is_visible_in_events_pane(ev, today=today)
    ]

    # Should only see the cloned event (on today's date)
    # The original non-recurring event from yesterday should be hidden
    # The original recurring event from yesterday should also be hidden (now has freq=none)
    assert len(all_events_day2) == 1
    assert all_events_day2[0].title == "Daily standup"
    assert all_events_day2[0].date == today

    # Verify the original events are in the repo but not visible
    all_events = list(repo.list_events())
    assert len(all_events) == 3  # 2 originals + 1 clone

    # Check each original is NOT visible
    original_meeting = [e for e in all_events if e.id == event1.id][0]
    assert not is_visible_in_events_pane(original_meeting, today=today)

    original_standup = [e for e in all_events if e.id == event2.id][0]
    assert not is_visible_in_events_pane(original_standup, today=today)


def test_debugging_visibility_logic(tmp_path):
    """Debug why events from yesterday might still appear."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteEventRepository(db)

    yesterday = date(2026, 1, 23)
    today = date(2026, 1, 24)

    # Create a simple event on Jan 23
    event = create_event(
        repo,
        CreateEventInput(
            title="Yesterday event",
            day=yesterday,
            start_time=time(14, 0),
            end_time=time(15, 0),
            notify=False,
        ),
    )

    # Reload from repo to ensure we're testing what's actually stored
    stored_event = repo.get_event(event.id)
    assert stored_event is not None

    print(f"\nEvent date: {stored_event.date}")
    print(f"Event repeat: {stored_event.repeat}")
    print(f"Event end_day_offset: {stored_event.end_day_offset}")
    print(f"Today: {today}")

    # Check visibility
    is_visible = is_visible_in_events_pane(stored_event, today=today)
    print(f"Is visible: {is_visible}")

    assert not is_visible, "Event from yesterday should NOT be visible today"
