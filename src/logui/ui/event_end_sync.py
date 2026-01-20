"""Pure logic for syncing event end fields in the Events form.

This used to live in the Events screen module, but it's easier to maintain and
reuse when kept separate from the Textual UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from logui.ui.parsing import parse_date_flexible, parse_time_flexible


@dataclass(frozen=True)
class EndSyncResult:
    end_day_value: str | None
    end_time_value: str | None
    duration_minutes: int | None
    end_day_autofilled: bool


def _is_time_input_ambiguous(raw: str) -> bool:
    """Check if a time input is ambiguous (could have more digits coming).

    Only single digits "1" or "2" are ambiguous (could be 10, 11, 12, etc.).
    Other single digits (3-9) are unambiguous.

    Examples:
    - "1" -> True (could be 1:00, 10:00, 11:00, etc.)
    - "2" -> True (could be 2:00, 20:00, 21:00, etc.)
    - "3" -> False (can only be 3:00)
    - "11" -> False (clearly 11:00)
    - "1:" -> False (user explicitly added colon)
    - "1:3" -> False (user is specifying minutes)
    """
    s = (raw or "").strip()
    if not s:
        return False
    # If it contains a colon, it's explicit
    if ":" in s:
        return False
    # Only single digits "1" or "2" are ambiguous
    if len(s) == 1 and s in ("1", "2"):
        return True
    return False


def _infer_end_day_offset_for_duration(
    *,
    start_t: time,
    end_t: time,
    end_day: date | None,
    start_day: date,
) -> int:
    if end_day is None:
        return 1 if end_t < start_t else 0
    return (end_day - start_day).days


def _compute_duration_minutes(
    *,
    start_day: date,
    start_t: time,
    end_t: time,
    end_day_offset: int,
) -> int | None:
    if end_day_offset < 0:
        return None
    start_dt = datetime.combine(start_day, start_t)
    end_dt = datetime.combine(start_day, end_t) + timedelta(days=end_day_offset)
    delta = end_dt - start_dt
    minutes = int(delta.total_seconds() // 60)
    if minutes < 0:
        return None
    return minutes


def _sync_end_fields_logic(
    *,
    changed_id: str,
    start_day: date,
    start_time_raw: str,
    end_day_raw: str,
    end_time_raw: str,
    duration_minutes: int | None,
    end_day_autofilled: bool,
    today: date,
) -> EndSyncResult:
    """Pure sync logic for end fields.

    Rules:
    - Do not auto-fill end_time when empty.
    - If start changes and end_time exists, update end_time to preserve stored duration.
    - Do not auto-fill end_day unless rollover (+1 day) is required.
    """

    start_time_s = (start_time_raw or "").strip()
    end_time_s = (end_time_raw or "").strip()
    end_day_s = (end_day_raw or "").strip()

    if not start_time_s:
        return EndSyncResult(None, None, duration_minutes, end_day_autofilled)

    try:
        start_t = parse_time_flexible(start_time_s)
    except Exception:  # noqa: BLE001
        return EndSyncResult(None, None, duration_minutes, end_day_autofilled)

    parsed_end_day: date | None = None
    if end_day_s:
        try:
            parsed_end_day = parse_date_flexible(end_day_s, today=today)
        except Exception:  # noqa: BLE001
            parsed_end_day = None

    # If user changes end_time, update stored duration (when possible) and set end_day only
    # when rollover is necessary.
    if changed_id == "end_time":
        if not end_time_s:
            # If user clears end_time, don't fight their edits by changing end_day.
            return EndSyncResult(None, None, None, end_day_autofilled)

        # If the input is ambiguous (e.g., single digit like "1"), don't apply rollover logic yet.
        # This prevents the issue where typing "11" triggers rollover on the first "1".
        if _is_time_input_ambiguous(end_time_s):
            # Still try to parse and update duration, but don't auto-fill end_day
            try:
                parse_time_flexible(end_time_s)
            except Exception:  # noqa: BLE001
                return EndSyncResult(None, None, duration_minutes, end_day_autofilled)

            # If end_day was previously autofilled and the user is typing a new time,
            # we should clear it to avoid confusion.
            if end_day_autofilled:
                return EndSyncResult("", None, None, False)

            # Otherwise, just keep things as they are without auto-filling
            return EndSyncResult(None, None, duration_minutes, end_day_autofilled)

        try:
            end_t = parse_time_flexible(end_time_s)
        except Exception:  # noqa: BLE001
            return EndSyncResult(None, None, duration_minutes, end_day_autofilled)

        end_day_offset = _infer_end_day_offset_for_duration(
            start_t=start_t,
            end_t=end_t,
            end_day=parsed_end_day,
            start_day=start_day,
        )
        new_duration = _compute_duration_minutes(
            start_day=start_day,
            start_t=start_t,
            end_t=end_t,
            end_day_offset=end_day_offset,
        )

        # Auto-fill end_day only if needed AND the field is currently empty.
        if not end_day_s and end_day_offset == 1:
            return EndSyncResult(
                start_day.fromordinal(start_day.toordinal() + 1).isoformat(),
                None,
                new_duration,
                True,
            )

        # If we had previously auto-filled end_day and rollover is no longer needed, clear it.
        if end_day_autofilled and end_day_offset == 0:
            # In edit mode we keep end_day filled; when no rollover is needed it should
            # match start_day.
            return EndSyncResult(start_day.isoformat(), None, new_duration, True)

        return EndSyncResult(None, None, new_duration, end_day_autofilled)

    # If user changes end_day manually, we don't override fields; just update duration if possible.
    if changed_id == "end_day":
        if not end_time_s:
            return EndSyncResult(None, None, duration_minutes, False)
        try:
            end_t = parse_time_flexible(end_time_s)
        except Exception:  # noqa: BLE001
            return EndSyncResult(None, None, duration_minutes, False)

        end_day_offset = _infer_end_day_offset_for_duration(
            start_t=start_t,
            end_t=end_t,
            end_day=parsed_end_day,
            start_day=start_day,
        )
        new_duration = _compute_duration_minutes(
            start_day=start_day,
            start_t=start_t,
            end_t=end_t,
            end_day_offset=end_day_offset,
        )
        return EndSyncResult(None, None, new_duration, False)

    # start_day / start_time changed
    if not end_time_s:
        # Important: do NOT auto-fill end_time. Defaults are applied on submit.
        return EndSyncResult(None, None, duration_minutes, end_day_autofilled)

    if duration_minutes is None:
        return EndSyncResult(None, None, duration_minutes, end_day_autofilled)

    new_end_dt = datetime.combine(start_day, start_t) + timedelta(minutes=duration_minutes)
    new_end_t = new_end_dt.time()
    new_offset = (new_end_dt.date() - start_day).days

    end_day_value: str | None = None
    autofilled = end_day_autofilled
    if end_day_autofilled:
        if new_offset >= 0:
            end_day_value = start_day.fromordinal(start_day.toordinal() + new_offset).isoformat()
            autofilled = True
    else:
        if not end_day_s and new_offset == 1:
            end_day_value = start_day.fromordinal(start_day.toordinal() + 1).isoformat()
            autofilled = True

    if new_offset < 0:
        return EndSyncResult(None, None, duration_minutes, end_day_autofilled)

    return EndSyncResult(end_day_value, new_end_t.strftime("%H:%M"), duration_minutes, autofilled)
