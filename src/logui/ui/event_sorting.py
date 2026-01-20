from __future__ import annotations

from datetime import date

from logui.domain.entities.event import Event


def event_list_sort_key(ev: Event) -> tuple[date, int, int, str]:
    """Sort key for the Events list.

    Order:
    - start day
    - all-day events first
    - start time (minutes from midnight)
    - stable tie-breaker (id)
    """

    all_day_rank = 0 if ev.start_time is None else 1
    minutes = -1
    if ev.start_time is not None:
        minutes = ev.start_time.hour * 60 + ev.start_time.minute
    return (ev.date, all_day_rank, minutes, str(ev.id))
