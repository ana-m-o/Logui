from __future__ import annotations

from datetime import date


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

    delta_days = (new_start_day - last_sync_start_day).days
    return last_sync_end_day.fromordinal(last_sync_end_day.toordinal() + delta_days)
