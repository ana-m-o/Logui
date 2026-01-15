from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import (
    Checkbox,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
)

from logui.domain.entities.event import Event, EventNote
from logui.domain.errors import ValidationError
from logui.domain.ports.events import EventRepository
from logui.ui.dates import (
    fmt_day_compact_friendly as _fmt_day_compact_friendly,
)
from logui.ui.dates import (
    fmt_day_full_friendly as _fmt_day_full_friendly,
)
from logui.ui.dates import (
    fmt_day_short_friendly as _fmt_day_short_friendly,
)
from logui.ui.screens.event_notes import EventNotesScreen
from logui.ui.screens.modals import ConfirmScreen
from logui.usecases.events import (
    CreateEventInput,
    UpdateEventPatch,
    create_event,
    toggle_event_notify,
    update_event,
)


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


def _format_event_notes_block(notes: list[EventNote]) -> str:
    lines: list[str] = []
    for n in notes:
        text = (n.text or "").strip()
        if not text:
            continue
        lines.append(f"- {text}")
    return "\n".join(lines)


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
                end_t = parse_time_flexible(end_time_s)
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


def today_local() -> date:
    return datetime.now().date()


def parse_time_flexible(raw: str) -> time:
    s = (raw or "").strip()
    if not s:
        raise ValidationError("time is empty")
    if ":" not in s:
        s = f"{s}:00"
    try:
        hh_s, mm_s = s.split(":", 1)
        hh = int(hh_s)
        mm = int(mm_s)
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError("out of range")
        return time(hh, mm)
    except Exception as e:  # noqa: BLE001
        raise ValidationError("Invalid time") from e


def parse_date_flexible(raw: str, *, today: date) -> date:
    s = (raw or "").strip()
    if not s:
        raise ValidationError("date is empty")

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:  # noqa: BLE001
            continue

    def _add_months(year: int, month: int, *, add: int) -> tuple[int, int]:
        total = (year * 12) + (month - 1) + add
        new_year = total // 12
        new_month = (total % 12) + 1
        return new_year, new_month

    # DD/MM -> next occurrence (if already passed this year, use next year)
    m = re.fullmatch(r"\s*(\d{1,2})/(\d{1,2})\s*", s)
    if m:
        day = int(m.group(1))
        month = int(m.group(2))
        try:
            cand = date(today.year, month, day)
        except Exception as e:  # noqa: BLE001
            raise ValidationError("Invalid date") from e

        if cand < today:
            try:
                return date(today.year + 1, month, day)
            except Exception as e:  # noqa: BLE001
                raise ValidationError("Invalid date") from e
        return cand

    # MM-DD -> next occurrence (if already passed this year, use next year)
    m = re.fullmatch(r"\s*(\d{1,2})-(\d{1,2})\s*", s)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        try:
            cand = date(today.year, month, day)
        except Exception as e:  # noqa: BLE001
            raise ValidationError("Invalid date") from e

        if cand < today:
            try:
                return date(today.year + 1, month, day)
            except Exception as e:  # noqa: BLE001
                raise ValidationError("Invalid date") from e
        return cand

    # DD -> next occurrence (if already passed this month, use next month)
    m = re.fullmatch(r"\s*(\d{1,2})\s*", s)
    if m:
        day = int(m.group(1))

        start_add = 0 if day >= today.day else 1
        for add in range(start_add, 24):
            y, mo = _add_months(today.year, today.month, add=add)
            try:
                cand = date(y, mo, day)
            except Exception:
                continue
            if cand >= today:
                return cand

        raise ValidationError("Invalid date")

    raise ValidationError("Invalid date")


def _add_1h_with_day_rollover(start_t: time) -> tuple[time, int]:
    base = datetime(2000, 1, 1, start_t.hour, start_t.minute)
    end = base + timedelta(hours=1)
    offset = 1 if end.date() != base.date() else 0
    return end.time(), offset


def fmt_day_full_friendly(day: date) -> str:
    return _fmt_day_full_friendly(day)


def fmt_day_short_friendly(day: date, *, today: date) -> str:
    return _fmt_day_short_friendly(day, today=today)


def _build_start_day_hint_text(
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
        effective_day = initial_start_day
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
    # Only check this if today parameter matches the actual current date.
    if start_time_s and not start_day_s and initial_start_day == today:
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


def _build_end_day_hint_text(
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


@dataclass(frozen=True)
class EventFormResult:
    title: str
    start_day: date
    start_time: time | None
    end_day: date | None
    end_time: time | None
    end_day_offset: int
    notify: bool
    notify_minutes_before: int | None


class EventFormScreen(ModalScreen[EventFormResult | None]):
    BINDINGS = [
        Binding("enter", "submit", "Save", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(
        self,
        *,
        title: str,
        initial: EventFormResult,
        prefill_dates: bool,
    ):
        super().__init__()
        self._dialog_title = title
        self._initial = initial
        self._prefill_dates = prefill_dates
        self.add_class("modal")
        self._syncing = False
        # In edit mode we prefill end_day and keep it synced unless user edits it.
        self._end_day_autofilled = bool(self._prefill_dates)

        self._last_sync_start_day: date = self._initial.start_day
        self._last_sync_end_day: date | None = None
        if self._prefill_dates:
            if self._initial.end_day_offset == 1:
                self._last_sync_end_day = self._initial.start_day.fromordinal(
                    self._initial.start_day.toordinal() + 1
                )
            elif self._initial.end_day_offset == 0:
                self._last_sync_end_day = self._initial.start_day

        self._duration_minutes: int | None = None
        if (
            self._initial.start_time is not None
            and self._initial.end_time is not None
            and self._initial.end_day_offset >= 0
        ):
            self._duration_minutes = _compute_duration_minutes(
                start_day=self._initial.start_day,
                start_t=self._initial.start_time,
                end_t=self._initial.end_time,
                end_day_offset=self._initial.end_day_offset,
            )

    def compose(self) -> ComposeResult:
        start_day_value = self._initial.start_day.isoformat() if self._prefill_dates else ""
        end_day_default = None
        if self._initial.end_day_offset == 1:
            end_day_default = self._initial.start_day.fromordinal(
                self._initial.start_day.toordinal() + 1
            )
        elif self._initial.end_day_offset == 0:
            end_day_default = self._initial.start_day
        end_day_value = ""
        if self._prefill_dates and end_day_default is not None:
            end_day_value = end_day_default.isoformat()

        yield Container(
            Label(self._dialog_title, id="form_title", classes="modal_title"),
            Static(
                "[dim]enter save • esc cancel[/dim]",
                id="form_help",
                classes="modal_help",
            ),
            Label("Title *"),
            Input(value=self._initial.title, id="title"),
            Label("Start (date and time)"),
            Horizontal(
                Input(
                    value=start_day_value,
                    placeholder=(
                        "2025-12-25, 5/7, 3/6/26 (empty = today)"
                    ),
                    id="start_day",
                ),
                Input(
                    value=_fmt_time(self._initial.start_time),
                    placeholder="9, 9:30, 09:00",
                    id="start_time",
                ),
                classes="modal_row",
            ),
            Static("", id="start_day_hint", classes="hint"),
            Label("End (date and time)"),
            Horizontal(
                Input(
                    value=end_day_value,
                    placeholder=(
                        "empty = same day. Multi-day: e.g. 30/1/26"
                    ),
                    id="end_day",
                ),
                Input(
                    value=_fmt_time(self._initial.end_time),
                    placeholder="empty = +1h (if start)",
                    id="end_time",
                ),
                classes="modal_row",
            ),
            Static("", id="end_day_hint", classes="hint"),
            Checkbox("Notify", value=self._initial.notify, id="notify"),
            Label("Notify (minutes before)"),
            Input(
                value=(
                    ""
                    if self._initial.notify_minutes_before is None
                    else str(self._initial.notify_minutes_before)
                ),
                placeholder="empty = at event time",
                id="notify_minutes_before",
            ),
            Static("", id="form_error", classes="modal_error"),
            id="event_form",
            classes="modal_box modal_w80",
        )

    def on_mount(self) -> None:
        self.query_one("#title", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        self._submit()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id in {"start_day", "start_time"}:
            self._update_start_day_hint()

        if event.input.id == "end_day":
            # User touched end_day; don't treat it as autofilled anymore.
            # (But ignore programmatic sync updates.)
            if not self._syncing:
                self._end_day_autofilled = False

        if event.input.id in {"start_day", "start_time", "end_time", "end_day"}:
            self._sync_end_fields(changed_id=event.input.id or "")
            self._update_end_day_hint()

        if event.input.id == "end_day":
            self._update_end_day_hint()

    def on_blur(self, event: events.Blur) -> None:
        """Handle blur events to apply rollover logic for ambiguous time inputs."""
        # When end_time loses focus and has an ambiguous value (1 or 2),
        # re-run sync to apply rollover logic now that user is done typing.
        if hasattr(event.control, "id") and event.control.id == "end_time":
            end_time_input = self.query_one("#end_time", Input)
            end_time_raw = (end_time_input.value or "").strip()
            
            # If it was ambiguous but now user is done, re-sync with force
            if end_time_raw and not _is_time_input_ambiguous(end_time_raw):
                self._sync_end_fields(changed_id="end_time")
                self._update_end_day_hint()

    def _update_start_day_hint(self) -> None:
        hint = self.query_one("#start_day_hint", Static)

        start_day_raw = (self.query_one("#start_day", Input).value or "").strip()
        start_time_raw = (self.query_one("#start_time", Input).value or "").strip()

        today = today_local()
        self._set_hint(
            hint,
            _build_start_day_hint_text(
                start_day_raw=start_day_raw,
                start_time_raw=start_time_raw,
                initial_start_day=self._initial.start_day,
                today=today,
            ),
        )

    def _update_end_day_hint(self) -> None:
        hint = self.query_one("#end_day_hint", Static)
        today = today_local()
        start_day_raw = (self.query_one("#start_day", Input).value or "").strip()
        end_day_raw = (self.query_one("#end_day", Input).value or "").strip()
        start_time_raw = (self.query_one("#start_time", Input).value or "").strip()
        end_time_raw = (self.query_one("#end_time", Input).value or "").strip()

        self._set_hint(
            hint,
            _build_end_day_hint_text(
                start_day_raw=start_day_raw,
                end_day_raw=end_day_raw,
                start_time_raw=start_time_raw,
                end_time_raw=end_time_raw,
                initial_start_day=self._initial.start_day,
                today=today,
            ),
        )

    def _set_hint(self, widget: Static, text: str) -> None:
        cleaned = (text or "").strip()
        widget.update(cleaned)
        if cleaned:
            widget.add_class("is-visible")
        else:
            widget.remove_class("is-visible")

    def _sync_end_fields(self, *, changed_id: str) -> None:
        if self._syncing:
            return

        try:
            self._syncing = True

            today = today_local()
            start_day_in = self.query_one("#start_day", Input)
            start_time_in = self.query_one("#start_time", Input)
            end_day_in = self.query_one("#end_day", Input)
            end_time_in = self.query_one("#end_time", Input)

            start_day_raw = (start_day_in.value or "").strip()
            start_time_raw = (start_time_in.value or "").strip()
            end_day_raw = (end_day_in.value or "").strip()
            end_time_raw = (end_time_in.value or "").strip()

            start_day = self._initial.start_day
            if start_day_raw:
                try:
                    start_day = parse_date_flexible(start_day_raw, today=today)
                except Exception:  # noqa: BLE001
                    return

            parsed_end_day: date | None = None
            if end_day_raw:
                try:
                    parsed_end_day = parse_date_flexible(end_day_raw, today=today)
                except Exception:  # noqa: BLE001
                    parsed_end_day = None

            # If the user changes start_day and end_day is present, shift end_day by the
            # same delta (preserve the event's day span), similar to how we preserve
            # duration when start_time changes.
            if (
                changed_id == "start_day"
                and parsed_end_day is not None
                and self._last_sync_end_day is not None
            ):
                delta_days = (start_day - self._last_sync_start_day).days
                if delta_days != 0:
                    new_end_day = self._last_sync_end_day.fromordinal(
                        self._last_sync_end_day.toordinal() + delta_days
                    )
                    new_raw = new_end_day.isoformat()
                    if end_day_in.value != new_raw:
                        end_day_in.value = new_raw
                    end_day_raw = new_raw
                    parsed_end_day = new_end_day

            result = _sync_end_fields_logic(
                changed_id=changed_id,
                start_day=start_day,
                start_time_raw=start_time_raw,
                end_day_raw=end_day_raw,
                end_time_raw=end_time_raw,
                duration_minutes=self._duration_minutes,
                end_day_autofilled=self._end_day_autofilled,
                today=today,
            )

            self._duration_minutes = result.duration_minutes
            self._end_day_autofilled = result.end_day_autofilled

            if result.end_time_value is not None and end_time_in.value != result.end_time_value:
                end_time_in.value = result.end_time_value

            if result.end_day_value is not None and end_day_in.value != result.end_day_value:
                end_day_in.value = result.end_day_value

            # Track the last effective values for future start_day shifts.
            self._last_sync_start_day = start_day
            if parsed_end_day is not None:
                self._last_sync_end_day = parsed_end_day
            elif end_day_in.value:
                try:
                    self._last_sync_end_day = parse_date_flexible(end_day_in.value, today=today)
                except Exception:  # noqa: BLE001
                    self._last_sync_end_day = None
            else:
                self._last_sync_end_day = None
        finally:
            self._syncing = False

    def _submit(self) -> None:
        error = self.query_one("#form_error", Static)
        error.update("")

        # Clear all error classes first
        for input_widget in self.query(Input):
            input_widget.remove_class("error")

        start_day_input = self.query_one("#start_day", Input)
        title_input = self.query_one("#title", Input)
        start_time_input = self.query_one("#start_time", Input)
        end_day_input = self.query_one("#end_day", Input)
        end_time_input = self.query_one("#end_time", Input)
        nmb_input = self.query_one("#notify_minutes_before", Input)

        start_day_raw = start_day_input.value.strip()
        title = title_input.value.strip()
        start_raw = start_time_input.value.strip()
        end_day_raw = end_day_input.value.strip()
        end_raw = end_time_input.value.strip()
        notify = self.query_one("#notify", Checkbox).value
        nmb_raw = nmb_input.value.strip()

        errors: list[str] = []

        today = today_local()
        if not start_day_raw:
            # In "New" this will be today; in "Edit" it preserves the existing date.
            start_day = self._initial.start_day
        else:
            try:
                start_day = parse_date_flexible(start_day_raw, today=today)
            except Exception:  # noqa: BLE001
                start_day = self._initial.start_day
                start_day_input.add_class("error")
                errors.append(
                    "Invalid date. Allowed formats: YYYY-MM-DD (2025-12-25), "
                    "DD/MM/YYYY (25/12/2025), DD/MM (5/9, uses current year), "
                    "DD/MM/YY (3/6/26), "
                    "MM-DD (12-25, uses current year) or "
                    "DD (25, uses current month). Empty = today"
                )

        if not title:
            title_input.add_class("error")
            errors.append("Title cannot be empty")

        start_t: time | None = None
        if start_raw:
            try:
                start_t = parse_time_flexible(start_raw)
            except Exception:  # noqa: BLE001
                start_time_input.add_class("error")
                errors.append(
                    "Invalid start time. Allowed formats: 9, 9:30, 09:00. "
                    "Empty = all day"
                )

        end_t: time | None = None
        if end_raw:
            try:
                end_t = parse_time_flexible(end_raw)
            except Exception:  # noqa: BLE001
                end_time_input.add_class("error")
                errors.append(
                    "Invalid end time. Allowed formats: 9, 9:30, 09:00. "
                    "Empty = +1h if there is a start"
                )

        end_day: date | None = None
        if end_day_raw:
            try:
                end_day = parse_date_flexible(end_day_raw, today=today)
            except Exception:  # noqa: BLE001
                end_day_input.add_class("error")
                errors.append(
                    "Invalid end date. Use the same formats as Start. "
                    "Empty = same day. Multi-day: enter a later date (e.g. 30/1/26)"
                )

        end_day_offset = 0

        if start_t is None and end_t is not None:
            start_time_input.add_class("error")
            end_time_input.add_class("error")
            errors.append(
                "End time requires a start time. Define start or leave end empty"
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
            end_day_input.add_class("error")
            errors.append("End date cannot be before start date")

        notify_minutes_before: int | None
        if not nmb_raw:
            notify_minutes_before = None
        else:
            try:
                notify_minutes_before = int(nmb_raw)
            except Exception:  # noqa: BLE001
                notify_minutes_before = None
                nmb_input.add_class("error")
                errors.append(
                    "Invalid minutes before. Use an integer (e.g.: 0, 5, 15). "
                    "Empty = at event time"
                )

        if notify_minutes_before is not None and notify_minutes_before < 0:
            nmb_input.add_class("error")
            errors.append("Minutes before cannot be negative. Use 0 or more")

        if start_t is not None and end_t is not None and end_day_offset >= 0:
            start_dt = datetime.combine(start_day, start_t)
            end_dt = datetime.combine(start_day, end_t) + timedelta(days=end_day_offset)
            if end_dt < start_dt:
                end_time_input.add_class("error")
                end_day_input.add_class("error")
                errors.append(
                    "End time must be >= start time. If it crosses midnight, "
                    "use a later end date or leave end empty"
                )

        if errors:
            error.update("[red]" + "\n".join(f"• {m}" for m in errors) + "[/red]")
            return

        self.dismiss(
            EventFormResult(
                title=title,
                start_day=start_day,
                start_time=start_t,
                end_day=end_day,
                end_time=end_t,
                end_day_offset=end_day_offset,
                notify=bool(notify),
                notify_minutes_before=notify_minutes_before,
            )
        )


class EventsPane(Container):
    BINDINGS = [
        Binding("n", "new", "New", show=False),
        Binding("enter", "edit", "Edit", show=False, priority=True),
        Binding("e", "edit", "Edit", show=False, priority=True),
        Binding("x", "delete", "Delete", show=False),
        Binding("a", "toggle_notify", "Toggle notify", show=False),
        Binding("r", "cycle_repeat", "Repeat", show=False),
        Binding("m", "notes", "Notes", show=False),
    ]

    def __init__(self, repo: EventRepository):
        super().__init__(id="events")
        self._repo = repo
        self._events: list[Event] = []

    def compose(self) -> ComposeResult:
        yield Container(
            Horizontal(
                Label("Events"),
                classes="page_header",
            ),
            Static(
                "[dim]n new • e/enter edit • x delete • a notify • r repeat (soon) • m notes[/dim]",
                classes="page_help",
            ),
            ListView(id="events_list", classes="event_list"),
        )

    def on_mount(self) -> None:
        self._refresh()
        # Keep temporal styling (in-progress/past) in sync with time.
        try:
            self.set_interval(15, self._refresh_temporal_styles)
        except Exception:  # noqa: BLE001
            pass

    def on_day_rollover(self, *, today: date) -> None:
        selected = self._selected_event()
        keep_id = str(selected.id) if selected is not None else None
        self._refresh(keep_id=keep_id, keep_scroll=True, focus=False, today=today)

    def _refresh_temporal_styles(self) -> None:
        if not self._events:
            return

        try:
            lv = self.query_one("#events_list", ListView)
        except Exception:  # noqa: BLE001
            return

        items = list(lv.query(ListItem))
        if not items:
            return

        now = datetime.now()
        for idx, ev in enumerate(self._events):
            if idx >= len(items):
                break
            item = items[idx]
            try:
                row = item.query_one(".event_row", Container)
            except Exception:  # noqa: BLE001
                continue
            self._apply_temporal_classes(row, ev, now=now)

    def on_click(self, event: events.Click) -> None:
        if event.chain < 2 or event.button != 1:
            return

        w = event.widget
        while w is not None and not isinstance(w, ListItem):
            w = getattr(w, "parent", None)
        if w is None:
            return

        list_view = getattr(w, "parent", None)
        while list_view is not None and not isinstance(list_view, ListView):
            list_view = getattr(list_view, "parent", None)
        if list_view is None:
            return

        if getattr(list_view, "id", None) != "events_list":
            return

        list_view.focus()
        self.call_later(self.action_edit)

    def _notify(self, message: str) -> None:
        notify = getattr(self.app, "notify", None)
        if callable(notify):
            notify(message)

    def _refresh(
        self,
        *,
        keep_id: str | None = None,
        keep_scroll: bool = False,
        focus: bool = True,
        today: date | None = None,
    ) -> None:
        today = today or today_local()
        now = datetime.now()
        
        # Filter events: show only those that are relevant for today or future.
        # Hide events that ended before today (fully in the past).
        def _is_visible(ev: Event) -> bool:
            # Calculate the end date of the event
            end_day = ev.date.fromordinal(ev.date.toordinal() + int(ev.end_day_offset or 0))
            
            # If event ends before today, it's in the past - don't show
            if end_day < today:
                return False
            
            # If event ends today or later, show it
            return True

        self._events = [ev for ev in self._repo.list_events() if _is_visible(ev)]

        def sort_key(ev: Event) -> tuple[date, int, int, str]:
            all_day_rank = 0 if ev.start_time is None else 1
            minutes = -1
            if ev.start_time is not None:
                minutes = ev.start_time.hour * 60 + ev.start_time.minute
            return (ev.date, all_day_rank, minutes, str(ev.id))

        self._events.sort(key=sort_key)

        lv = self.query_one("#events_list", ListView)
        old_index = lv.index or 0
        old_scroll_y = getattr(lv, "scroll_y", None) if keep_scroll else None
        lv.clear()

        if not self._events:
            lv.append(ListItem(Label("(No events) — press n to create")))
            if focus:
                lv.focus()
            return

        for ev in self._events:
            lv.append(self._build_list_item(ev, now=now))

        selected_idx = 0
        if keep_id:
            for idx, ev in enumerate(self._events):
                if str(ev.id) == keep_id:
                    selected_idx = idx
                    break
        else:
            selected_idx = max(0, min(old_index, len(self._events) - 1))

        lv.index = selected_idx
        if old_scroll_y is not None:
            try:
                lv.scroll_y = old_scroll_y
            except Exception:  # noqa: BLE001
                pass
        if focus:
            lv.focus()

    def _format_row(self, ev: Event) -> str:
        today = today_local()
        start_day = ev.date
        end_day = start_day.fromordinal(start_day.toordinal() + int(ev.end_day_offset or 0))

        day_part = self._fmt_day_friendly(start_day, today)

        time_part = "All day"
        if ev.start_time is None:
            if ev.end_day_offset and ev.end_day_offset > 0:
                day_part = f"{day_part}–{self._fmt_day_friendly(end_day, today)}"
        else:
            start_s = ev.start_time.strftime("%H:%M")
            end_s = ev.end_time.strftime("%H:%M") if ev.end_time else "??"
            if ev.end_day_offset and ev.end_day_offset > 0:
                time_part = f"{start_s}–{self._fmt_day_friendly(end_day, today)} {end_s}"
            else:
                time_part = f"{start_s}–{end_s}"

        repeat_part = ""
        if ev.repeat and isinstance(ev.repeat, dict):
            freq = str(ev.repeat.get("freq") or "")
            if freq and freq != "none":
                repeat_part = f" ({freq})"

        return f"{day_part} {time_part}  {ev.title}{repeat_part}"

    def _event_notify_glyph(self, ev: Event) -> str:
        return "🕭" if ev.notify else " "

    def _event_time_bounds(self, ev: Event) -> tuple[datetime, datetime]:
        start_dt = datetime.combine(ev.date, ev.start_time or time(0, 0))

        if ev.start_time is None:
            # All-day events span full days; represent the end as an exclusive bound.
            days = int(ev.end_day_offset or 0) + 1
            end_dt = datetime.combine(ev.date, time(0, 0)) + timedelta(days=days)
            return start_dt, end_dt

        if ev.end_time is None:
            return start_dt, start_dt + timedelta(hours=1)

        end_dt = datetime.combine(ev.date, ev.end_time) + timedelta(
            days=int(ev.end_day_offset or 0)
        )
        return start_dt, end_dt

    def _apply_temporal_classes(self, row: Container, ev: Event, *, now: datetime) -> None:
        row.remove_class("is_past")
        row.remove_class("is_in_progress")

        start_dt, end_dt = self._event_time_bounds(ev)
        if end_dt <= now:
            row.add_class("is_past")
        elif start_dt <= now < end_dt:
            row.add_class("is_in_progress")

    def _build_list_item(self, ev: Event, *, now: datetime) -> ListItem:
        main = self._format_row(ev)
        notes_block = _format_event_notes_block(ev.notes or [])
        notes_w = Static(notes_block, classes="event_row_notes", markup=False)
        if notes_block:
            notes_w.add_class("is-visible")

        row = Container(
            Horizontal(
                Static(self._event_notify_glyph(ev), classes="event_notify", markup=False),
                Label(main, classes="event_row_main"),
                classes="event_row_main_line",
            ),
            notes_w,
            classes="event_row",
        )
        self._apply_temporal_classes(row, ev, now=now)

        return ListItem(row)

    def _fmt_day_friendly(self, day: date, today: date) -> str:
        return _fmt_day_compact_friendly(day, today=today)

    def _selected_event(self) -> Event | None:
        if not self._events:
            return None
        lv = self.query_one("#events_list", ListView)
        idx = lv.index or 0
        if idx < 0 or idx >= len(self._events):
            return None
        return self._events[idx]

    def _selected_index(self) -> int | None:
        if not self._events:
            return None
        lv = self.query_one("#events_list", ListView)
        idx = lv.index or 0
        if idx < 0 or idx >= len(self._events):
            return None
        return idx

    def _update_selected_item_in_place(self, updated: Event, *, focus: bool = True) -> None:
        idx = self._selected_index()
        if idx is None:
            return

        lv = self.query_one("#events_list", ListView)
        items = list(lv.query(ListItem))
        if idx >= len(items):
            self._refresh()
            return

        item = items[idx]
        try:
            item.query_one(".event_notify", Static).update(self._event_notify_glyph(updated))

            label = item.query_one(".event_row_main", Label)
            label.update(self._format_row(updated))

            notes_block = _format_event_notes_block(updated.notes or [])
            notes_w = item.query_one(".event_row_notes", Static)
            notes_w.update(notes_block)
            if (notes_block or "").strip():
                notes_w.add_class("is-visible")
            else:
                notes_w.remove_class("is-visible")

            row = item.query_one(".event_row", Container)
            self._apply_temporal_classes(row, updated, now=datetime.now())
        except Exception:  # noqa: BLE001
            self._refresh()
            return

        # Update the event in the internal list
        self._events[idx] = updated
        
        # Check if the event should be reordered
        def sort_key(ev: Event) -> tuple[date, int, int, str]:
            all_day_rank = 0 if ev.start_time is None else 1
            minutes = -1
            if ev.start_time is not None:
                minutes = ev.start_time.hour * 60 + ev.start_time.minute
            return (ev.date, all_day_rank, minutes, str(ev.id))
        
        # Create a sorted copy to find new position
        sorted_events = sorted(self._events, key=sort_key)
        new_idx = next((i for i, ev in enumerate(sorted_events) if ev.id == updated.id), idx)
        
        # If position changed, reorder using move_child
        if new_idx != idx:
            # Update internal list to match sorted order
            self._events = sorted_events
            
            # Move the DOM node to the new position
            if new_idx < idx:
                # Moving up - insert before the item at new_idx
                if new_idx < len(items):
                    lv.move_child(item, before=items[new_idx])
            else:
                # Moving down - insert after the item at new_idx
                if new_idx < len(items):
                    lv.move_child(item, after=items[new_idx])
            
            lv.index = new_idx
        else:
            lv.index = idx
        
        if focus:
            lv.focus()

    def action_new(self) -> None:
        initial = EventFormResult(
            title="",
            start_day=today_local(),
            start_time=None,
            end_day=None,
            end_time=None,
            end_day_offset=0,
            notify=True,
            notify_minutes_before=None,
        )
        screen = EventFormScreen(title="New event", initial=initial, prefill_dates=False)

        def _on_dismiss(result: EventFormResult | None) -> None:
            if result is None:
                return
            try:
                ev = create_event(
                    self._repo,
                    CreateEventInput(
                        title=result.title,
                        day=result.start_day,
                        start_time=result.start_time,
                        end_time=result.end_time,
                        end_day_offset=result.end_day_offset,
                        notify=result.notify,
                        notify_minutes_before=result.notify_minutes_before,
                    ),
                    default_notify_minutes_before=0,
                )
                self._refresh()
                self._notify(f"Evento creado: {ev.title}")
            except Exception as e:  # noqa: BLE001
                self._notify(f"Error creando evento: {e}")

        self.app.push_screen(screen, callback=_on_dismiss)

    def action_edit(self) -> None:
        ev = self._selected_event()
        if ev is None:
            return

        initial = EventFormResult(
            title=ev.title,
            start_day=ev.date,
            start_time=ev.start_time,
            end_day=None,
            end_time=ev.end_time,
            end_day_offset=ev.end_day_offset,
            notify=ev.notify,
            notify_minutes_before=ev.notify_minutes_before,
        )
        screen = EventFormScreen(title="Editar evento", initial=initial, prefill_dates=True)
        ev_id = ev.id

        def _on_dismiss(result: EventFormResult | None) -> None:
            if result is None:
                return
            try:
                updated = update_event(
                    self._repo,
                    ev_id,
                    UpdateEventPatch(
                        title=result.title,
                        day=result.start_day,
                        start_time=result.start_time,
                        end_time=result.end_time,
                        end_day_offset=result.end_day_offset,
                        notify=result.notify,
                        notify_minutes_before=result.notify_minutes_before,
                    ),
                    default_notify_minutes_before=0,
                )
                self._update_selected_item_in_place(updated)
                self._notify(f"Evento actualizado: {updated.title}")
            except Exception as e:  # noqa: BLE001
                self._notify(f"Error actualizando evento: {e}")

        self.app.push_screen(screen, callback=_on_dismiss)

    def action_delete(self) -> None:
        ev = self._selected_event()
        if ev is None:
            return

        ev_id = ev.id
        title = ev.title

        def _on_confirm(ok: bool) -> None:
            if not ok:
                return
            deleted = self._repo.delete_event(ev_id)
            if deleted:
                self._refresh()
                self._notify("Evento borrado")

        self.app.push_screen(ConfirmScreen(f"Delete event '{title}'?"), callback=_on_confirm)

    def action_toggle_notify(self) -> None:
        ev = self._selected_event()
        if ev is None:
            return
        try:
            updated = toggle_event_notify(self._repo, ev.id, default_notify_minutes_before=0)
            self._update_selected_item_in_place(updated)
            self._notify(f"Notificación: {'ON' if updated.notify else 'OFF'}")
        except Exception as e:  # noqa: BLE001
            self._notify(f"Error: {e}")

    def action_cycle_repeat(self) -> None:
        # MVP: repeat rules are not yet implemented (no occurrence expansion).
        self._notify("Repeat is not yet implemented")

    def action_notes(self) -> None:
        ev = self._selected_event()
        if ev is None:
            return

        def _on_changed(updated: Event) -> None:
            self._update_selected_item_in_place(updated, focus=False)

        def _on_dismiss(_result: object) -> None:
            self.query_one("#events_list", ListView).focus()

        self.app.push_screen(
            EventNotesScreen(self._repo, ev, on_changed=_on_changed),
            callback=_on_dismiss,
        )


def default_data_dir() -> Path:
    return Path.home() / ".logui"


def ensure_data_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _fmt_time(t: time | None) -> str:
    return t.strftime("%H:%M") if t else ""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
