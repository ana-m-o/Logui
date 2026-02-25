from __future__ import annotations

from datetime import date, datetime, time, timedelta

from logui.domain.entities.event import Event


def get_display_date_for_event(ev: Event, *, today: date) -> date:
    """Get the date that should be displayed for an event.
    
    For recurring events, returns the next occurrence date.
    For non-recurring events, returns the base date.
    """
    if ev.repeat and isinstance(ev.repeat, dict):
        freq = ev.repeat.get("freq")
        if freq and freq != "none":
            # If the event occurs today, show today
            if ev.occurs_on(today):
                return today
            
            # If the event has passed for today, show the next occurrence
            next_date = ev.next_occurrence(after=today - timedelta(days=1))
            if next_date and next_date >= today:
                return next_date
    
    return ev.date


def is_visible_in_events_pane(ev: Event, *, today: date) -> bool:
    """Whether an event should be shown in the Events list.

    Shows events that:
    - Are on or after today (for non-recurring events), OR
    - Are today's past events (show events from today even if they ended), OR
    - Are multi-day events still ongoing (end date >= today), OR
    - Are recurring events that have a next occurrence (including today or future)
    """

    # For events with recurrence, show if they have a next occurrence
    if ev.repeat and isinstance(ev.repeat, dict):
        freq = ev.repeat.get("freq")
        if freq and freq != "none":
            # Show if there's a next occurrence (today or future)
            display_date = get_display_date_for_event(ev, today=today)
            return display_date >= today

    # For non-recurring events (including events that were recurring but are now cloned),
    # check if the event's end date (considering multi-day offset) is today or later
    end_day = ev.date
    if ev.end_day_offset and ev.end_day_offset > 0:
        end_day = ev.date + timedelta(days=ev.end_day_offset)

    return end_day >= today


def temporal_classnames(ev: Event, *, now: datetime) -> set[str]:
    """Compute CSS classnames for an event row based on time."""
    
    today = now.date()
    display_date = get_display_date_for_event(ev, today=today)

    start_dt = datetime.combine(display_date, ev.start_time or time(0, 0))

    if ev.start_time is None:
        days = int(ev.end_day_offset or 0) + 1
        end_dt = datetime.combine(display_date, time(0, 0)) + timedelta(days=days)
    elif ev.end_time is None:
        end_dt = start_dt + timedelta(hours=1)
    else:
        end_dt = datetime.combine(display_date, ev.end_time) + timedelta(
            days=int(ev.end_day_offset or 0)
        )

    classes: set[str] = set()
    if end_dt <= now:
        classes.add("is_past")
    elif start_dt <= now < end_dt:
        classes.add("is_in_progress")
    return classes
