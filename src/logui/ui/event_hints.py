"""Pure hint-building logic for the Events form.

The Events screen uses these helpers to render contextual hints while the user
edits date/time fields. Keeping them here reduces the size and responsibilities
of the Textual screen module.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from logui.ui.dates import fmt_day_full_friendly, fmt_day_short_friendly
from logui.ui.parsing import parse_date_flexible, parse_time_flexible


def _add_1h_with_day_rollover(start_t: time) -> tuple[time, int]:
    base = datetime(2000, 1, 1, start_t.hour, start_t.minute)
    end = base + timedelta(hours=1)
    offset = 1 if end.date() != base.date() else 0
    return end.time(), offset


def build_start_day_hint_text(
    *,
    start_day_raw: str,
    start_time_raw: str,
    initial_start_day: date,
    today: date,
) -> str:
    start_day_s = (start_day_raw or "").strip()
    start_time_s = (start_time_raw or "").strip()

    start_time_label = ""
    if start_time_s:
        try:
            start_t = parse_time_flexible(start_time_s)
        except Exception:  # noqa: BLE001
            start_t = None
        if start_t is not None:
            start_time_label = f" {start_t.strftime('%H:%M')}"

    # Determine effective start day (matches submit behavior).
    if not start_day_s:
        # Empty date always means today (matches _submit behavior)
        effective_day = today
        if effective_day == today:
            day_label = f"Today, {effective_day.year}"
        else:
            day_label = fmt_day_short_friendly(effective_day, today=today)
    else:
        try:
            effective_day = parse_date_flexible(start_day_s, today=today)
        except Exception:  # noqa: BLE001
            return ""
        day_label = fmt_day_short_friendly(effective_day, today=today)

    all_day = not bool(start_time_label)
    suffix = " (all day)" if all_day else start_time_label

    # If date is empty (default = today) and the user enters a past time,
    # show a warning in the same style as past-date warnings.
    if start_time_s and not start_day_s:
        actual_today = datetime.now().date()
        if today == actual_today:
            try:
                start_t = parse_time_flexible(start_time_s)
            except Exception:  # noqa: BLE001
                start_t = None
            if start_t is not None:
                now = datetime.now().time()
                now_min = time(now.hour, now.minute)
                if start_t < now_min:
                    return (
                        f"[dim]{fmt_day_full_friendly(today)} {start_t.strftime('%H:%M')} "
                        f"(is a past time)[/dim]"
                    )

    if start_day_s and effective_day < today:
        return f"[dim]{fmt_day_full_friendly(effective_day)}{suffix} (is a past date)[/dim]"
    return f"[dim]{day_label}{suffix}[/dim]"


def build_end_day_hint_text(
    *,
    start_day_raw: str,
    end_day_raw: str,
    start_time_raw: str,
    end_time_raw: str,
    initial_start_day: date,
    today: date,
) -> str:
    start_day_s = (start_day_raw or "").strip()
    end_day_s = (end_day_raw or "").strip()
    start_time_s = (start_time_raw or "").strip()
    end_time_s = (end_time_raw or "").strip()

    start_day = initial_start_day
    if start_day_s:
        try:
            start_day = parse_date_flexible(start_day_s, today=today)
        except Exception:  # noqa: BLE001
            return ""

    # Only hide for single-day all-day events.
    if not start_time_s and not end_day_s:
        return ""

    end_day = start_day
    if end_day_s:
        try:
            end_day = parse_date_flexible(end_day_s, today=today)
        except Exception:  # noqa: BLE001
            return ""

    if not start_time_s:
        return f"[dim]{fmt_day_short_friendly(end_day, today=today)} (all day)[/dim]"

    try:
        start_t = parse_time_flexible(start_time_s)
    except Exception:  # noqa: BLE001
        return ""

    end_t: time | None = None
    defaulted = False

    if end_time_s:
        try:
            end_t = parse_time_flexible(end_time_s)
        except Exception:  # noqa: BLE001
            end_t = None
    else:
        end_t, inferred_offset = _add_1h_with_day_rollover(start_t)
        defaulted = True
        if not end_day_s:
            end_day = start_day.fromordinal(start_day.toordinal() + inferred_offset)

    # If end_time is present but end_day is empty, infer rollover (+1) only.
    if end_t is not None and end_time_s and not end_day_s and end_t < start_t:
        end_day = start_day.fromordinal(start_day.toordinal() + 1)

    if end_t is None:
        return f"[dim]{fmt_day_short_friendly(end_day, today=today)}[/dim]"

    tag = " (default +1h)" if defaulted else ""
    return (
        f"[dim]{fmt_day_short_friendly(end_day, today=today)} {end_t.strftime('%H:%M')}{tag}[/dim]"
    )
