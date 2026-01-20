from __future__ import annotations

from datetime import date


def shift_end_day_with_start_day_delta(
    *,
    new_start_day: date,
    previous_start_day: date,
    previous_end_day: date,
) -> date:
    """Shift an end day by the delta implied by a start day change.

    Used by the Events form: when the user edits `start_day` and `end_day` is
    present, we preserve the event's day-span by shifting `end_day` by the same
    delta.
    """

    delta_days = (new_start_day - previous_start_day).days
    return previous_end_day.fromordinal(previous_end_day.toordinal() + delta_days)


def maybe_shift_end_day_on_start_day_change(
    *,
    changed_id: str,
    new_start_day: date,
    last_sync_start_day: date | None,
    last_sync_end_day: date | None,
) -> date | None:
    """Return a shifted end day if start_day changed and we have sync history."""

    if changed_id != "start_day":
        return None
    if last_sync_start_day is None or last_sync_end_day is None:
        return None

    if new_start_day == last_sync_start_day:
        return None

    return shift_end_day_with_start_day_delta(
        new_start_day=new_start_day,
        previous_start_day=last_sync_start_day,
        previous_end_day=last_sync_end_day,
    )
