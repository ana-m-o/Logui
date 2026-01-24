"""Test that recurring events/tasks remain visible across days."""
from datetime import date, time

from logui.domain.entities.event import Event
from logui.ui.event_temporal import is_visible_in_events_pane


def test_non_recurring_event_hides_after_end_date():
    """Non-recurring events disappear after their end date."""
    ev = Event.create("Meeting", day=date(2026, 1, 24))
    
    assert is_visible_in_events_pane(ev, today=date(2026, 1, 24))
    assert not is_visible_in_events_pane(ev, today=date(2026, 1, 25))


def test_daily_recurring_event_stays_visible():
    """Daily recurring events remain visible on future days."""
    ev = Event.create("Daily standup", day=date(2026, 1, 24), start_time=time(9, 0))
    ev.repeat = {"freq": "daily"}
    
    assert is_visible_in_events_pane(ev, today=date(2026, 1, 24))
    assert is_visible_in_events_pane(ev, today=date(2026, 1, 25))
    assert is_visible_in_events_pane(ev, today=date(2026, 1, 26))
    assert is_visible_in_events_pane(ev, today=date(2026, 2, 1))


def test_weekly_recurring_event_stays_visible():
    """Weekly recurring events remain visible on future weeks."""
    ev = Event.create("Weekly review", day=date(2026, 1, 24))  # Friday
    ev.repeat = {"freq": "weekly"}
    
    assert is_visible_in_events_pane(ev, today=date(2026, 1, 24))
    assert is_visible_in_events_pane(ev, today=date(2026, 1, 30))  # Next week
    assert is_visible_in_events_pane(ev, today=date(2026, 2, 6))   # Week after


def test_recurring_event_with_until_hides_after_end():
    """Recurring events with 'until' date stop appearing after that date."""
    ev = Event.create("Limited series", day=date(2026, 1, 24))
    ev.repeat = {"freq": "daily", "until": "2026-01-26"}
    
    assert is_visible_in_events_pane(ev, today=date(2026, 1, 24))
    assert is_visible_in_events_pane(ev, today=date(2026, 1, 25))
    assert is_visible_in_events_pane(ev, today=date(2026, 1, 26))
    assert not is_visible_in_events_pane(ev, today=date(2026, 1, 27))


def test_recurring_event_hides_before_start_date():
    """Recurring events don't appear before their start date."""
    ev = Event.create("Future recurring", day=date(2026, 1, 30))
    ev.repeat = {"freq": "daily"}
    
    assert not is_visible_in_events_pane(ev, today=date(2026, 1, 24))
    assert not is_visible_in_events_pane(ev, today=date(2026, 1, 29))
    assert is_visible_in_events_pane(ev, today=date(2026, 1, 30))
    assert is_visible_in_events_pane(ev, today=date(2026, 1, 31))
