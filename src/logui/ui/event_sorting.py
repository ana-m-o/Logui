from __future__ import annotations

from datetime import date

from logui.domain.entities.event import Event


def event_list_sort_key(ev: Event, *, today: date | None = None) -> tuple[date, int, int, str]:
    """Sort key for the Events list.

    Order:
    - display day (for recurring events, this is the next occurrence)
    - all-day events first
    - start time (minutes from midnight)
    - stable tie-breaker (id)
    """
    from logui.ui.event_temporal import get_display_date_for_event
    from logui.ui.parsing import today_local

    if today is None:
        today = today_local()

    display_date = get_display_date_for_event(ev, today=today)

    all_day_rank = 0 if ev.start_time is None else 1
    minutes = -1
    if ev.start_time is not None:
        minutes = ev.start_time.hour * 60 + ev.start_time.minute
    return (display_date, all_day_rank, minutes, str(ev.id))
