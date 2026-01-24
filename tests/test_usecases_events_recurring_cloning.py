"""Tests for recurring event cloning behavior."""

from datetime import date, time

from logui.infrastructure.repositories.events_repo_json import JsonEventRepository
from logui.usecases.events import CreateEventInput, create_event, process_recurring_events


def test_process_recurring_events_clones_past_events(tmp_path):
    """Past recurring events should be cloned for next occurrence."""
    repo = JsonEventRepository(tmp_path / "events.json")
    
    # Create a daily recurring event on Jan 20
    event = create_event(
        repo,
        CreateEventInput(
            title="Daily standup",
            day=date(2026, 1, 20),
            start_time=time(9, 0),
            end_time=time(9, 30),
            notify=False,
            repeat={"freq": "daily"},
        ),
    )
    
    # Process on Jan 24 (4 days later)
    new_events = process_recurring_events(repo, today=date(2026, 1, 24))
    
    # Should have created new event for next occurrence (today or later)
    assert len(new_events) == 1
    new_event = new_events[0]
    assert new_event.title == "Daily standup"
    assert new_event.date >= date(2026, 1, 24)  # Today or later
    assert new_event.start_time == time(9, 0)
    assert new_event.repeat == {"freq": "daily"}
    
    # Original event should no longer be recurring
    all_events = list(repo.list_events())
    original = [e for e in all_events if e.id == event.id][0]
    assert original.repeat == {"freq": "none"}
    assert original.date == date(2026, 1, 20)  # Original date preserved


def test_process_recurring_events_does_not_clone_future_events(tmp_path):
    """Future recurring events should not be cloned."""
    repo = JsonEventRepository(tmp_path / "events.json")
    
    # Create event for tomorrow
    event = create_event(
        repo,
        CreateEventInput(
            title="Future event",
            day=date(2026, 1, 25),
            start_time=time(10, 0),
            notify=False,
            repeat={"freq": "weekly"},
        ),
    )
    
    # Process on Jan 24 (event is still in future)
    new_events = process_recurring_events(repo, today=date(2026, 1, 24))
    
    # Should not clone
    assert len(new_events) == 0
    
    # Event should still be recurring
    all_events = list(repo.list_events())
    assert len(all_events) == 1
    assert all_events[0].repeat == {"freq": "weekly"}


def test_process_recurring_events_weekly_cloning(tmp_path):
    """Weekly recurring event should clone to next week."""
    repo = JsonEventRepository(tmp_path / "events.json")
    
    # Create weekly event on Jan 17 (Friday)
    event = create_event(
        repo,
        CreateEventInput(
            title="Weekly review",
            day=date(2026, 1, 17),
            start_time=time(14, 0),
            notify=False,
            repeat={"freq": "weekly"},
        ),
    )
    
    # Process on Jan 24
    new_events = process_recurring_events(repo, today=date(2026, 1, 24))
    
    assert len(new_events) == 1
    assert new_events[0].date == date(2026, 1, 24)  # Next Friday


def test_process_recurring_events_respects_until(tmp_path):
    """Events with 'until' should not clone after that date."""
    repo = JsonEventRepository(tmp_path / "events.json")
    
    event = create_event(
        repo,
        CreateEventInput(
            title="Limited series",
            day=date(2026, 1, 20),
            start_time=time(10, 0),
            notify=False,
            repeat={"freq": "daily", "until": "2026-01-20"},
        ),
    )
    
    # Process on Jan 24
    new_events = process_recurring_events(repo, today=date(2026, 1, 24))
    
    # Should not clone (past 'until' date)
    assert len(new_events) == 0


def test_process_recurring_events_clones_notes(tmp_path):
    """Cloned events should include notes from original."""
    repo = JsonEventRepository(tmp_path / "events.json")
    
    event = create_event(
        repo,
        CreateEventInput(
            title="Event with notes",
            day=date(2026, 1, 20),
            notify=False,
            repeat={"freq": "daily"},
        ),
    )
    
    # Add note
    from logui.usecases.events import add_event_note
    updated = add_event_note(repo, event.id, "Important note")
    
    # Process on Jan 24
    new_events = process_recurring_events(repo, today=date(2026, 1, 24))
    
    assert len(new_events) == 1
    assert len(new_events[0].notes) == 1
    assert new_events[0].notes[0].text == "Important note"


def test_process_recurring_events_only_clones_once(tmp_path):
    """Calling process multiple times should not create duplicates."""
    repo = JsonEventRepository(tmp_path / "events.json")
    
    event = create_event(
        repo,
        CreateEventInput(
            title="Daily task",
            day=date(2026, 1, 20),
            notify=False,
            repeat={"freq": "daily"},
        ),
    )
    
    # Process first time
    new_events1 = process_recurring_events(repo, today=date(2026, 1, 24))
    assert len(new_events1) == 1
    
    # Process again (should not clone again since original is no longer recurring)
    new_events2 = process_recurring_events(repo, today=date(2026, 1, 24))
    assert len(new_events2) == 0
    
    # Total events: original (no recurrence) + 1 clone (with recurrence)
    all_events = list(repo.list_events())
    assert len(all_events) == 2
