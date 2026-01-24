from __future__ import annotations

from datetime import date, datetime, time, timedelta

from logui.domain.entities.event import Event


def is_visible_in_events_pane(ev: Event, *, today: date) -> bool:
    """Whether an event should be shown in the Events list.

    Shows events that:
    - Are on or after today (for non-recurring events), OR
    - Are today's past events (show events from today even if they ended), OR
    - Are multi-day events still ongoing (end date >= today)
    """
    
    # For events with recurrence, only show if they occur today or in the future
    if ev.repeat and isinstance(ev.repeat, dict):
        freq = ev.repeat.get("freq")
        if freq and freq != "none":
            # Only show if the event's date is today or in the future
            return ev.date >= today
    
    # For non-recurring events (including events that were recurring but are now cloned),
    # check if the event's end date (considering multi-day offset) is today or later
    end_day = ev.date
    if ev.end_day_offset and ev.end_day_offset > 0:
        from datetime import timedelta
        end_day = ev.date + timedelta(days=ev.end_day_offset)
    
    return end_day >= today


def temporal_classnames(ev: Event, *, now: datetime) -> set[str]:
    """Compute CSS classnames for an event row based on time."""

    start_dt = datetime.combine(ev.date, ev.start_time or time(0, 0))

    if ev.start_time is None:
        days = int(ev.end_day_offset or 0) + 1
        end_dt = datetime.combine(ev.date, time(0, 0)) + timedelta(days=days)
    elif ev.end_time is None:
        end_dt = start_dt + timedelta(hours=1)
    else:
        end_dt = datetime.combine(ev.date, ev.end_time) + timedelta(days=int(ev.end_day_offset or 0))

    classes: set[str] = set()
    if end_dt <= now:
        classes.add("is_past")
    elif start_dt <= now < end_dt:
        classes.add("is_in_progress")
    return classes
