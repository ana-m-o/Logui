from __future__ import annotations

from datetime import date, datetime, time, timedelta

from logui.domain.entities.event import Event


def is_visible_in_events_pane(ev: Event, *, today: date) -> bool:
    """Whether an event should be shown in the Events list.

    Shows events that:
    - Ended on or after today (for non-recurring events), OR
    - Occur on today (for recurring events), OR
    - Have active recurrence (ongoing daily/weekly/monthly)
    """
    
    # If event has recurrence, check if it occurs on today or has active recurrence
    if ev.repeat and isinstance(ev.repeat, dict):
        freq = ev.repeat.get("freq")
        if freq and freq != "none":
            # Check if event occurs on today
            if ev.occurs_on(today):
                return True
            
            # Check if recurrence is still active (not past 'until' date)
            until = ev.repeat.get("until")
            if until is None:
                # No end date, recurrence continues indefinitely
                return ev.date <= today
            
            # Has 'until' date, check if we're still within the recurrence period
            if isinstance(until, str):
                from datetime import datetime
                try:
                    until_date = datetime.fromisoformat(until).date()
                    return ev.date <= today <= until_date
                except Exception:  # noqa: BLE001
                    pass
            elif isinstance(until, date):
                return ev.date <= today <= until
    
    # For non-recurring events, show if they haven't ended yet
    end_day = ev.date.fromordinal(ev.date.toordinal() + int(ev.end_day_offset or 0))
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
