from __future__ import annotations

from datetime import date, time

from logui.ui.event_end_sync import _compute_duration_minutes


def initial_end_day_default(*, start_day: date, end_day_offset: int) -> date | None:
    """Compute the default end day for prefilling the form in edit mode."""

    if end_day_offset == 1:
        return start_day.fromordinal(start_day.toordinal() + 1)
    if end_day_offset == 0:
        return start_day
    return None


def initial_last_sync_end_day(
    *, start_day: date, end_day_offset: int, prefill_dates: bool
) -> date | None:
    """Compute the initial tracked end day used for start_day shifting logic."""

    if not prefill_dates:
        return None
    return initial_end_day_default(start_day=start_day, end_day_offset=end_day_offset)


def initial_duration_minutes(
    *,
    start_day: date,
    start_time: time | None,
    end_time: time | None,
    end_day_offset: int,
) -> int | None:
    if start_time is None or end_time is None or end_day_offset < 0:
        return None

    return _compute_duration_minutes(
        start_day=start_day,
        start_t=start_time,
        end_t=end_time,
        end_day_offset=end_day_offset,
    )
