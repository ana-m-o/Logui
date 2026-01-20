from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from logui.ui.event_hints import _add_1h_with_day_rollover
from logui.ui.parsing import parse_date_flexible, parse_time_flexible


@dataclass(frozen=True)
class FormError:
    message: str
    field_id: str | None = None


@dataclass(frozen=True)
class ParsedEventForm:
    title: str
    start_day: date
    start_time: time | None
    end_day: date | None
    end_time: time | None
    end_day_offset: int
    notify: bool
    notify_minutes_before: int | None


_INVALID_START_DATE_MSG = (
    "Invalid date. Allowed formats: YYYY-MM-DD (2025-12-25), "
    "DD/MM/YYYY (25/12/2025), DD/MM (5/9, uses current year), "
    "DD/MM/YY (3/6/26), "
    "MM-DD (12-25, uses current year) or "
    "DD (25, uses current month). Empty = today"
)

_INVALID_END_DATE_MSG = (
    "Invalid end date. Use the same formats as Start. "
    "Empty = same day. Multi-day: enter a later date (e.g. 30/1/26)"
)

_INVALID_START_TIME_MSG = "Invalid start time. Allowed formats: 9, 9:30, 09:00. Empty = all day"

_INVALID_END_TIME_MSG = (
    "Invalid end time. Allowed formats: 9, 9:30, 09:00. "
    "Empty = +1h if there is a start"
)


def parse_event_form_submission(
    *,
    start_day_raw: str,
    title_raw: str,
    start_time_raw: str,
    end_day_raw: str,
    end_time_raw: str,
    notify: bool,
    notify_minutes_before_raw: str,
    initial_start_day: date,
    today: date,
) -> tuple[ParsedEventForm | None, list[FormError]]:
    """Parse and validate the Event form inputs.

    This is intentionally UI-agnostic (returns structured errors instead of
    touching Textual widgets).
    """

    errors: list[FormError] = []

    start_day_s = (start_day_raw or "").strip()
    title = (title_raw or "").strip()
    start_time_s = (start_time_raw or "").strip()
    end_day_s = (end_day_raw or "").strip()
    end_time_s = (end_time_raw or "").strip()
    nmb_s = (notify_minutes_before_raw or "").strip()

    if not start_day_s:
        # Empty date always means today, regardless of new/edit mode.
        start_day = today
    else:
        try:
            start_day = parse_date_flexible(start_day_s, today=today)
        except Exception:  # noqa: BLE001
            start_day = initial_start_day
            errors.append(FormError(_INVALID_START_DATE_MSG, field_id="start_day"))

    if not title:
        errors.append(FormError("Title cannot be empty", field_id="title"))

    start_t: time | None = None
    if start_time_s:
        try:
            start_t = parse_time_flexible(start_time_s)
        except Exception:  # noqa: BLE001
            errors.append(FormError(_INVALID_START_TIME_MSG, field_id="start_time"))

    end_t: time | None = None
    if end_time_s:
        try:
            end_t = parse_time_flexible(end_time_s)
        except Exception:  # noqa: BLE001
            errors.append(FormError(_INVALID_END_TIME_MSG, field_id="end_time"))

    end_day: date | None = None
    if end_day_s:
        try:
            end_day = parse_date_flexible(end_day_s, today=today)
        except Exception:  # noqa: BLE001
            errors.append(FormError(_INVALID_END_DATE_MSG, field_id="end_day"))

    end_day_offset = 0

    if start_t is None and end_t is not None:
        errors.append(
            FormError(
                "End time requires a start time. Define start or leave end empty",
                field_id="start_time",
            )
        )
        errors.append(
            FormError(
                "End time requires a start time. Define start or leave end empty",
                field_id="end_time",
            )
        )

    # Compute end_day_offset and defaults.
    if start_t is None:
        # All-day event (single or multi-day range). Times must be empty.
        if end_day is not None:
            end_day_offset = (end_day - start_day).days
        else:
            end_day_offset = 0
    else:
        # Timed event.
        if end_t is None:
            end_t, inferred_offset = _add_1h_with_day_rollover(start_t)
            if end_day is None:
                end_day = start_day.fromordinal(start_day.toordinal() + inferred_offset)
            end_day_offset = (end_day - start_day).days
        else:
            if end_day is None:
                # If user didn't provide an end date, only infer same-day or +1.
                end_day_offset = 1 if end_t < start_t else 0
                end_day = start_day.fromordinal(start_day.toordinal() + end_day_offset)
            else:
                end_day_offset = (end_day - start_day).days

    if end_day_offset < 0:
        errors.append(FormError("End date cannot be before start date", field_id="end_day"))

    notify_minutes_before: int | None
    if not nmb_s:
        notify_minutes_before = None
    else:
        try:
            notify_minutes_before = int(nmb_s)
        except Exception:  # noqa: BLE001
            notify_minutes_before = None
            errors.append(
                FormError(
                    "Invalid minutes before. Use an integer (e.g.: 0, 5, 15). "
                    "Empty = at event time",
                    field_id="notify_minutes_before",
                )
            )

    if notify_minutes_before is not None and notify_minutes_before < 0:
        errors.append(
            FormError(
                "Minutes before cannot be negative. Use 0 or more",
                field_id="notify_minutes_before",
            )
        )

    if start_t is not None and end_t is not None and end_day_offset >= 0:
        start_dt = datetime.combine(start_day, start_t)
        end_dt = datetime.combine(start_day, end_t) + timedelta(days=end_day_offset)
        if end_dt < start_dt:
            errors.append(
                FormError(
                    "End time must be >= start time. If it crosses midnight, "
                    "use a later end date or leave end empty",
                    field_id="end_time",
                )
            )
            errors.append(
                FormError(
                    "End time must be >= start time. If it crosses midnight, "
                    "use a later end date or leave end empty",
                    field_id="end_day",
                )
            )

    if errors:
        return None, errors

    parsed = ParsedEventForm(
        title=title,
        start_day=start_day,
        start_time=start_t,
        end_day=end_day,
        end_time=end_t,
        end_day_offset=end_day_offset,
        notify=bool(notify),
        notify_minutes_before=notify_minutes_before,
    )
    return parsed, []
