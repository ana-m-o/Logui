from __future__ import annotations

from datetime import date, datetime, time, timedelta

from logui.domain.entities.event import Event


def is_visible_in_events_pane(ev: Event, *, today: date) -> bool:
    """Whether an event should be shown in the Events list.

    Matches the current UI behavior: hide events that ended before `today`.
    """

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
