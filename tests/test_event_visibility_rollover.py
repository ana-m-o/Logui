"""Test to verify events from yesterday disappear after day rollover."""

from datetime import date, time

from logui.domain.entities.event import Event
from logui.ui.event_temporal import is_visible_in_events_pane


def test_event_from_yesterday_is_not_visible_today():
    """Events from previous day should not be visible."""
    yesterday = date(2026, 1, 23)
    today = date(2026, 1, 24)

    # Regular event from yesterday
    ev = Event.create("Yesterday's meeting", day=yesterday, start_time=time(10, 0))

    # Should be visible yesterday
    assert is_visible_in_events_pane(ev, today=yesterday)

    # Should NOT be visible today
    assert not is_visible_in_events_pane(ev, today=today)


def test_event_with_repeat_none_from_yesterday_is_not_visible():
    """Events with repeat='none' from yesterday should not be visible."""
    yesterday = date(2026, 1, 23)
    today = date(2026, 1, 24)

    ev = Event.create("Meeting", day=yesterday, start_time=time(10, 0))
    ev.repeat = {"freq": "none"}

    # Should NOT be visible today
    assert not is_visible_in_events_pane(ev, today=today)


def test_recurring_event_from_yesterday_not_visible_after_cloning():
    """Recurring events from yesterday should be visible showing next occurrence."""
    yesterday = date(2026, 1, 23)
    today = date(2026, 1, 24)

    ev = Event.create("Daily standup", day=yesterday, start_time=time(9, 0))
    ev.repeat = {"freq": "daily"}

    # With the next-occurrence model, recurring events show their next occurrence
    # A daily event that started yesterday should be visible showing today's occurrence
    assert is_visible_in_events_pane(ev, today=today)
    
    # And the display date should be today (the next occurrence)
    from logui.ui.event_temporal import get_display_date_for_event
    display_date = get_display_date_for_event(ev, today=today)
    assert display_date == today


def test_multiday_event_starting_yesterday_still_visible():
    """Multi-day events that started yesterday but haven't ended should be visible."""
    yesterday = date(2026, 1, 23)
    today = date(2026, 1, 24)

    # 3-day event starting yesterday
    ev = Event.create("Conference", day=yesterday)
    ev.end_day_offset = 2  # Ends on Jan 25

    # Should be visible (event is ongoing)
    assert is_visible_in_events_pane(ev, today=today)


def test_multiday_event_that_ended_yesterday_not_visible():
    """Multi-day events that ended yesterday should not be visible."""
    two_days_ago = date(2026, 1, 22)
    today = date(2026, 1, 24)

    # 2-day event that ended yesterday
    ev = Event.create("Workshop", day=two_days_ago)
    ev.end_day_offset = 1  # Ended on Jan 23

    # Should NOT be visible (event ended)
    assert not is_visible_in_events_pane(ev, today=today)

def test_recurring_event_shows_next_occurrence_when_current_ends():
    """When a recurring event's current occurrence ends, show the next one."""
    yesterday = date(2026, 1, 23)
    today = date(2026, 1, 24)
    tomorrow = date(2026, 1, 25)

    # Weekly event on Thursdays (yesterday was Thursday)
    ev = Event.create("Team meeting", day=yesterday, start_time=time(15, 0))
    ev.repeat = {"freq": "weekly"}  # Repeats every Thursday

    # Should be visible showing next Thursday's occurrence
    assert is_visible_in_events_pane(ev, today=today)
    
    from logui.ui.event_temporal import get_display_date_for_event
    next_thursday = yesterday.fromordinal(yesterday.toordinal() + 7)
    display_date = get_display_date_for_event(ev, today=today)
    assert display_date == next_thursday