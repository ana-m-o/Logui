from __future__ import annotations

from datetime import date, datetime, time, timedelta

from logui.domain.entities.event import Event


def event_end_day(ev: Event) -> date:
    return ev.date.fromordinal(ev.date.toordinal() + int(ev.end_day_offset or 0))


def is_visible_in_events_pane(ev: Event, *, today: date) -> bool:
    """Whether an event should be shown in the Events list.

    Matches the current UI behavior: hide events that ended before `today`.
    """

    return event_end_day(ev) >= today


def event_time_bounds(ev: Event) -> tuple[datetime, datetime]:
    """Return (start_dt, end_dt) for temporal styling.

    Notes:
    - All-day events span full days; end is an exclusive bound.
    - Missing end_time is treated as a 1h duration.
    """

    start_dt = datetime.combine(ev.date, ev.start_time or time(0, 0))

    if ev.start_time is None:
        days = int(ev.end_day_offset or 0) + 1
        end_dt = datetime.combine(ev.date, time(0, 0)) + timedelta(days=days)
        return start_dt, end_dt

    if ev.end_time is None:
        return start_dt, start_dt + timedelta(hours=1)

    end_dt = datetime.combine(ev.date, ev.end_time) + timedelta(days=int(ev.end_day_offset or 0))
    return start_dt, end_dt


def temporal_classnames(ev: Event, *, now: datetime) -> set[str]:
    """Compute CSS classnames for an event row based on time."""

    start_dt, end_dt = event_time_bounds(ev)

    classes: set[str] = set()
    if end_dt <= now:
        classes.add("is_past")
    elif start_dt <= now < end_dt:
        classes.add("is_in_progress")
    return classes
