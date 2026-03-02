from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import UUID

from textual import events, on
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
    Select,
    Static,
)

from logui.domain.entities.event import Event, EventNote
from logui.domain.ports.events import EventRepository
from logui.ui.dates import fmt_day_compact_friendly
from logui.ui.event_end_day_shift import maybe_shift_end_day_on_start_day_change
from logui.ui.event_end_sync import _is_time_input_ambiguous, _sync_end_fields_logic
from logui.ui.event_form_state import (
    initial_duration_minutes,
    initial_end_day_default,
    initial_last_sync_end_day,
)
from logui.ui.event_form_submit import parse_event_form_submission
from logui.ui.event_hints import build_end_day_hint_text, build_start_day_hint_text
from logui.ui.event_row_format import (
    event_notify_glyph,
    format_event_notes_block,
    format_event_row,
)
from logui.ui.event_sorting import event_list_sort_key
from logui.ui.event_temporal import (
    is_visible_in_events_pane,
    temporal_classnames,
)
from logui.ui.parsing import parse_date_flexible, today_local
from logui.ui.screens.event_notes import EventNotesScreen
from logui.ui.screens.modals import ConfirmScreen
from logui.usecases.events import (
    CreateEventInput,
    UpdateEventPatch,
    create_event,
    toggle_event_notify,
    update_event,
)

_log = logging.getLogger(__name__)

try:
    from textual.css.query import NoMatches, TooManyMatches
except Exception:  # noqa: BLE001
    NoMatches = TooManyMatches = Exception  # type: ignore[misc,assignment]


_REPEAT_FREQ_OPTIONS: list[tuple[str, str]] = [
    ("None", "none"),
    ("Daily", "daily"),
    ("Weekly", "weekly"),
    ("Monthly", "monthly"),
]


def _format_event_notes_block(notes: list[EventNote]) -> str:
    # Keep this symbol for tests/import stability.
    return format_event_notes_block(notes)


def _build_start_day_hint_text(
    *,
    start_day_raw: str,
    start_time_raw: str,
    initial_start_day: date,
    today: date,
) -> str:
    return build_start_day_hint_text(
        start_day_raw=start_day_raw,
        start_time_raw=start_time_raw,
        initial_start_day=initial_start_day,
        today=today,
    )


def _build_end_day_hint_text(
    *,
    start_day_raw: str,
    end_day_raw: str,
    start_time_raw: str,
    end_time_raw: str,
    initial_start_day: date,
    today: date,
) -> str:
    return build_end_day_hint_text(
        start_day_raw=start_day_raw,
        end_day_raw=end_day_raw,
        start_time_raw=start_time_raw,
        end_time_raw=end_time_raw,
        initial_start_day=initial_start_day,
        today=today,
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
    repeat: dict[str, any] | None


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
        self._last_sync_end_day = initial_last_sync_end_day(
            start_day=self._initial.start_day,
            end_day_offset=self._initial.end_day_offset,
            prefill_dates=self._prefill_dates,
        )

        self._duration_minutes = initial_duration_minutes(
            start_day=self._initial.start_day,
            start_time=self._initial.start_time,
            end_time=self._initial.end_time,
            end_day_offset=self._initial.end_day_offset,
        )

        # Extract repeat info
        self._current_freq = "none"
        self._current_days_str = ""

        if initial.repeat and isinstance(initial.repeat, dict):
            self._current_freq = initial.repeat.get("freq", "none")
            if self._current_freq == "weekly":
                weekdays = initial.repeat.get("weekdays", [])
                if weekdays:
                    # Convert weekday numbers to abbreviations
                    day_abbr = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
                    self._current_days_str = ", ".join(day_abbr[d] for d in sorted(weekdays))
            elif self._current_freq == "monthly":
                monthdays = initial.repeat.get("monthdays", [])
                if monthdays:
                    self._current_days_str = ", ".join(str(d) for d in sorted(monthdays))

    def compose(self) -> ComposeResult:
        start_day_value = self._initial.start_day.isoformat() if self._prefill_dates else ""
        end_day_default = initial_end_day_default(
            start_day=self._initial.start_day,
            end_day_offset=self._initial.end_day_offset,
        )
        end_day_value = ""
        if self._prefill_dates and end_day_default is not None:
            end_day_value = end_day_default.isoformat()

        # Determine initial days string for repeat
        initial_days_str = self._current_days_str
        if not initial_days_str and self._initial.start_day:
            if self._current_freq == "weekly":
                day_abbr = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
                initial_days_str = day_abbr[self._initial.start_day.weekday()]
            elif self._current_freq == "monthly":
                initial_days_str = str(self._initial.start_day.day)

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
                    placeholder=("2025-12-25, 5/7, 3/6/26 (empty = today)"),
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
                    placeholder=("empty = same day. Multi-day: e.g. 30/1/26"),
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
            Horizontal(
                Container(
                    Label("Repeat"),
                    Select(
                        _REPEAT_FREQ_OPTIONS,
                        value=self._current_freq,
                        id="repeat_freq",
                    ),
                    classes="half_col",
                ),
                Container(
                    Label("Days (e.g. mon, wed, fri)"),
                    Input(
                        value=initial_days_str,
                        placeholder="mon, tue, wed, thu, fri, sat, sun",
                        id="repeat_weekdays",
                    ),
                    id="repeat_days_container_weekly",
                    disabled=True,
                ),
                Container(
                    Label("Days of month (e.g. 1, 15, 30)"),
                    Input(
                        value=initial_days_str,
                        placeholder="1, 15, 30",
                        id="repeat_monthdays",
                    ),
                    id="repeat_days_container_monthly",
                    disabled=True,
                ),
                classes="modal_row",
            ),
            Checkbox("Notify", value=self._initial.notify, id="notify", classes="mt-1"),
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
        self._apply_repeat_freq_ui(self._current_freq)

    def _apply_repeat_freq_ui(self, freq: str) -> None:
        weekly_container = self.query_one("#repeat_days_container_weekly", Container)
        monthly_container = self.query_one("#repeat_days_container_monthly", Container)
        start_day_input = self.query_one("#start_day", Input)

        freq = (freq or "none").strip() or "none"

        # Mirror behavior: enabling repetition implies having a base date.
        if freq != "none":
            start_raw = (start_day_input.value or "").strip()
            if not start_raw:
                start_day_input.value = today_local().isoformat()
                self._update_start_day_hint()

        if freq == "weekly":
            weekly_container.display = True
            weekly_container.disabled = False
            monthly_container.display = False
            monthly_container.disabled = True

            days_input = weekly_container.query_one("#repeat_weekdays", Input)
            if not (days_input.value or "").strip():
                start_raw = (start_day_input.value or "").strip()
                try:
                    start_date = (
                        parse_date_flexible(start_raw, today=today_local())
                        if start_raw
                        else today_local()
                    )
                except Exception:  # noqa: BLE001
                    start_date = today_local()
                day_abbr = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
                days_input.value = day_abbr[start_date.weekday()]

        elif freq == "monthly":
            weekly_container.display = False
            weekly_container.disabled = True
            monthly_container.display = True
            monthly_container.disabled = False

            days_input = monthly_container.query_one("#repeat_monthdays", Input)
            if not (days_input.value or "").strip():
                start_raw = (start_day_input.value or "").strip()
                try:
                    start_date = (
                        parse_date_flexible(start_raw, today=today_local())
                        if start_raw
                        else today_local()
                    )
                except Exception:  # noqa: BLE001
                    start_date = today_local()
                days_input.value = str(start_date.day)

        else:
            weekly_container.display = False
            weekly_container.disabled = True
            monthly_container.display = False
            monthly_container.disabled = True

    @on(Select.Changed, "#repeat_freq")
    def _on_repeat_freq_changed(self, event: Select.Changed) -> None:
        new_freq = str(event.value) if event.value else "none"
        self._apply_repeat_freq_ui(new_freq)

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
            if parsed_end_day is not None:
                shifted = maybe_shift_end_day_on_start_day_change(
                    changed_id=changed_id,
                    new_start_day=start_day,
                    last_sync_start_day=self._last_sync_start_day,
                    last_sync_end_day=self._last_sync_end_day,
                )
                if shifted is not None:
                    new_raw = shifted.isoformat()
                    if end_day_in.value != new_raw:
                        end_day_in.value = new_raw
                    end_day_raw = new_raw
                    parsed_end_day = shifted

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
        title_raw = title_input.value.strip()
        start_raw = start_time_input.value.strip()
        end_day_raw = end_day_input.value.strip()
        end_raw = end_time_input.value.strip()
        notify = self.query_one("#notify", Checkbox).value
        nmb_raw = nmb_input.value.strip()

        today = today_local()
        parsed, form_errors = parse_event_form_submission(
            start_day_raw=start_day_raw,
            title_raw=title_raw,
            start_time_raw=start_raw,
            end_day_raw=end_day_raw,
            end_time_raw=end_raw,
            notify=bool(notify),
            notify_minutes_before_raw=nmb_raw,
            initial_start_day=self._initial.start_day,
            today=today,
        )

        if form_errors:
            for err in form_errors:
                if err.field_id:
                    try:
                        self.query_one(f"#{err.field_id}", Input).add_class("error")
                    except (NoMatches, TooManyMatches, AttributeError) as e:
                        _log.debug("Failed marking error field %s: %s", err.field_id, e)

            error.update("[red]" + "\n".join(f"• {e.message}" for e in form_errors) + "[/red]")
            return

        assert parsed is not None

        # Build repeat dict
        repeat_freq = str(self.query_one("#repeat_freq", Select).value or "none")
        repeat_dict: dict[str, Any] | None = None

        if repeat_freq and repeat_freq != "none":
            repeat_dict = {"freq": repeat_freq}

            if repeat_freq == "weekly":
                weekly_container = self.query_one("#repeat_days_container_weekly", Container)
                days_input = weekly_container.query_one("#repeat_weekdays", Input)
                days_text = (days_input.value or "").strip().upper()

                if not days_text:
                    days_input.add_class("error")
                    error.update(
                        "[red]• Weekly repeat requires at least one day (e.g., mon, wed, fri)[/red]"
                    )
                    return
                else:
                    # Parse day abbreviations: mon, tue, wed, thu, fri, sat, sun
                    day_mapping = {
                        "MON": 0,
                        "TUE": 1,
                        "WED": 2,
                        "THU": 3,
                        "FRI": 4,
                        "SAT": 5,
                        "SUN": 6,
                    }
                    parts = [p.strip().upper() for p in days_text.split(",")]
                    weekdays = []
                    for part in parts:
                        if part in day_mapping:
                            weekdays.append(day_mapping[part])
                        else:
                            days_input.add_class("error")
                            error.update(
                                f"[red]• Invalid weekday: {part}. Use mon, tue, wed, thu, fri, sat, sun[/red]"
                            )
                            return

                    if weekdays:
                        repeat_dict["weekdays"] = sorted(set(weekdays))

            elif repeat_freq == "monthly":
                monthly_container = self.query_one("#repeat_days_container_monthly", Container)
                days_input = monthly_container.query_one("#repeat_monthdays", Input)
                days_text = (days_input.value or "").strip()

                if not days_text:
                    days_input.add_class("error")
                    error.update(
                        "[red]• Monthly repeat requires at least one day (e.g., 1, 15, 30)[/red]"
                    )
                    return
                else:
                    # Parse day numbers: 1-31
                    parts = [p.strip() for p in days_text.split(",")]
                    monthdays = []
                    for part in parts:
                        try:
                            day_num = int(part)
                            if 1 <= day_num <= 31:
                                monthdays.append(day_num)
                            else:
                                days_input.add_class("error")
                                error.update(f"[red]• Day {day_num} must be between 1 and 31[/red]")
                                return
                        except ValueError:
                            days_input.add_class("error")
                            error.update(f"[red]• Invalid day number: {part}[/red]")
                            return

                    if monthdays:
                        repeat_dict["monthdays"] = sorted(set(monthdays))

        self.dismiss(
            EventFormResult(
                title=parsed.title,
                start_day=parsed.start_day,
                start_time=parsed.start_time,
                end_day=parsed.end_day,
                end_time=parsed.end_time,
                end_day_offset=parsed.end_day_offset,
                notify=parsed.notify,
                notify_minutes_before=parsed.notify_minutes_before,
                repeat=repeat_dict,
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
        self._events_to_hide: dict[UUID, float] = {}  # event_id -> timestamp when ended
        self._auto_hide_timer: Any = None

    def compose(self) -> ComposeResult:
        yield Container(
            Horizontal(
                Label("Events"),
                classes="page_header",
            ),
            Static(
                "[dim]n new • e/enter edit • x delete • a notify • r repeat • m notes[/dim]",
                classes="page_help",
            ),
            ListView(id="events_list", classes="event_list"),
        )

    def on_mount(self) -> None:
        self._refresh()
        # Keep temporal styling (in-progress/past) in sync with time.
        try:
            self.set_interval(15, self._refresh_temporal_styles)
        except Exception as e:  # noqa: BLE001
            _log.debug("Failed starting events temporal refresh: %s", e)

    def on_day_rollover(self, *, today: date) -> None:
        # Process recurring events that need to be cloned
        from logui.usecases.events import process_recurring_events

        process_recurring_events(self._repo, today=today)

        # Force a complete refresh without keeping old selection
        # (the selected event might be from yesterday and no longer visible)
        self._refresh(keep_id=None, keep_scroll=False, focus=False, today=today)

    def _refresh_temporal_styles(self) -> None:
        if not self._events:
            return

        try:
            lv = self.query_one("#events_list", ListView)
        except (NoMatches, TooManyMatches, AttributeError):
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
            except (NoMatches, TooManyMatches, AttributeError):
                continue
            self._apply_temporal_classes(row, ev, now=now)
            
            # Update the event row text to reflect current temporal state (e.g., "Now" vs "Today")
            try:
                label = row.query_one(".event_row_main", Label)
                label.update(self._format_row(ev))
            except (NoMatches, TooManyMatches, AttributeError):
                pass

        # Check if any events should be auto-hidden
        self._check_and_schedule_auto_hide(now)

    def _check_and_schedule_auto_hide(self, now: datetime) -> None:
        """Check if any events have ended and should be auto-hidden."""
        # Check if auto-hide is enabled
        auto_hide_enabled = False
        try:
            from logui.usecases.config import ConfigRepository

            config_repo = getattr(self.app, "_config_repo", None)
            if config_repo and isinstance(config_repo, ConfigRepository):
                config = config_repo.load()
                auto_hide_enabled = config.ui.auto_hide_completed
        except Exception:  # noqa: BLE001
            pass

        if not auto_hide_enabled:
            self._events_to_hide.clear()
            return

        # Find events that just ended and mark them for hiding
        import time

        current_time = time.time()

        for ev in self._events:
            if ev.start_time is None:
                continue  # All-day events don't auto-hide

            # Skip if already scheduled
            if ev.id in self._events_to_hide:
                continue

            # Calculate end datetime
            from datetime import timedelta

            start_dt = datetime.combine(ev.date, ev.start_time)
            if ev.end_time is None:
                end_dt = start_dt + timedelta(hours=1)
            else:
                end_dt = datetime.combine(ev.date, ev.end_time) + timedelta(
                    days=int(ev.end_day_offset or 0)
                )

            # If event just ended, schedule for removal
            if end_dt <= now:
                self._events_to_hide[ev.id] = current_time

        # Remove events that have been scheduled for 5+ seconds
        events_to_remove = []
        for event_id, marked_time in list(self._events_to_hide.items()):
            if current_time - marked_time >= 5.0:
                events_to_remove.append(event_id)

        for event_id in events_to_remove:
            self._remove_event_from_list(event_id)
            self._events_to_hide.pop(event_id, None)

    def _remove_event_from_list(self, event_id: UUID) -> None:
        """Remove an event from the ListView without refreshing the entire list."""
        try:
            lv = self.query_one("#events_list", ListView)

            # Find the index of the event in _events
            idx = next((i for i, ev in enumerate(self._events) if ev.id == event_id), None)
            if idx is None:
                return

            # Remove from internal list
            self._events.pop(idx)

            # Get the ListItem and remove it (like move_child does)
            items = list(lv.query(ListItem))
            if idx < len(items):
                item_to_remove = items[idx]
                item_to_remove.remove()
                self._notify("Event archived")

            # If list is now empty, show the empty message
            if not self._events:
                lv.clear()
                lv.append(ListItem(Label("(No events) — press n to create")))

        except Exception:  # noqa: BLE001
            # Fallback to full refresh if something goes wrong
            self._refresh()

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

        self._events = [
            ev for ev in self._repo.list_events() if is_visible_in_events_pane(ev, today=today)
        ]

        # Check if auto-hide is enabled
        auto_hide_enabled = False
        try:
            from logui.domain.ports.config import ConfigRepository

            config_repo = getattr(self.app, "_config_repo", None)
            if config_repo and isinstance(config_repo, ConfigRepository):
                config = config_repo.load()
                auto_hide_enabled = config.ui.auto_hide_completed
        except Exception:  # noqa: BLE001
            pass

        # Filter out ended events from today if auto_hide is enabled
        if auto_hide_enabled:
            filtered_events: list[Event] = []
            for ev in self._events:
                end_day = ev.date.fromordinal(ev.date.toordinal() + int(ev.end_day_offset or 0))
                # Hide events that ended today (end_day == today and already passed)
                if end_day == today:
                    # Check if the event has actually ended (time-wise)
                    if ev.start_time is None:
                        # All-day event ends at end of day
                        end_dt = datetime.combine(today, time(23, 59, 59))
                    elif ev.end_time is None:
                        # No end time, assume 1 hour duration
                        end_dt = datetime.combine(ev.date, ev.start_time) + timedelta(hours=1)
                    else:
                        end_dt = datetime.combine(ev.date, ev.end_time) + timedelta(
                            days=int(ev.end_day_offset or 0)
                        )

                    if now >= end_dt:
                        continue  # Skip this ended event

                filtered_events.append(ev)
            self._events = filtered_events

        self._events.sort(key=lambda ev: event_list_sort_key(ev, today=today))

        lv = self.query_one("#events_list", ListView)
        had_focus = lv.has_focus
        old_index = lv.index or 0
        old_scroll_y = getattr(lv, "scroll_y", None) if keep_scroll else None
        lv.clear()

        if not self._events:
            lv.append(ListItem(Label("(No events) — press n to create")))
            if focus or had_focus:
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

        lv.index = None
        lv.index = selected_idx
        if old_scroll_y is not None:
            try:
                lv.scroll_y = old_scroll_y
            except Exception as e:  # noqa: BLE001
                _log.debug("Failed restoring events scroll position: %s", e)
        if focus or had_focus:
            lv.focus()

        # Update event count in sidebar
        try:
            if hasattr(self.app, "update_nav_counts"):
                self.app.update_nav_counts()  # type: ignore[attr-defined]
        except Exception as e:  # noqa: BLE001
            _log.debug("Failed updating nav counts from EventsPane: %s", e)

    def _format_row(self, ev: Event) -> str:
        today = today_local()
        now = datetime.now()
        is_in_progress = "is_in_progress" in temporal_classnames(ev, now=now)
        
        def fmt_with_now_support(d: date) -> str:
            formatted = self._fmt_day_friendly(d, today)
            # Show "Now" instead of "Today" when event is in progress
            if is_in_progress and d == today and formatted.startswith("[bold]Today[/bold]"):
                return formatted.replace("[bold]Today[/bold] -", "[bold]Now[/bold] -", 1)
            return formatted
        
        return format_event_row(
            ev,
            today=today,
            fmt_day_friendly=fmt_with_now_support,
        )

    def _event_notify_glyph(self, ev: Event) -> str:
        return event_notify_glyph(ev)

    def _apply_temporal_classes(self, row: Container, ev: Event, *, now: datetime) -> None:
        row.remove_class("is_past")
        row.remove_class("is_in_progress")

        for class_name in temporal_classnames(ev, now=now):
            row.add_class(class_name)

    def _format_repeat_text(self, ev: Event) -> str:
        """Format the repeat indicator text for an event."""
        if not ev.repeat or not isinstance(ev.repeat, dict):
            return ""

        freq = str(ev.repeat.get("freq") or "")
        if not freq or freq == "none":
            return ""

        if freq == "daily":
            return " 🔁 daily"

        # Day name abbreviations (3 letters)
        _WEEKDAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

        if freq == "weekly":
            weekdays = ev.repeat.get("weekdays")
            if weekdays and isinstance(weekdays, list) and len(weekdays) > 0:
                # Sort and format weekday names
                day_names = [_WEEKDAY_NAMES[day] for day in sorted(weekdays) if 0 <= day < 7]
                if day_names:
                    return f" 🔁 {', '.join(day_names)}"
            # Fallback to base date's weekday if no weekdays specified
            if ev.date:
                day_name = ev.date.strftime("%A").lower()[:3]
                return f" 🔁 {day_name}"
            return " 🔁 weekly"

        if freq == "monthly":
            monthdays = ev.repeat.get("monthdays")
            if monthdays and isinstance(monthdays, list) and len(monthdays) > 0:
                # Sort and format day numbers
                day_nums = [str(day) for day in sorted(monthdays) if 1 <= day <= 31]
                if day_nums:
                    return f" 🔁 {', '.join(day_nums)}"
            # Fallback to base date's day if no monthdays specified
            if ev.date:
                day_num = ev.date.day
                return f" 🔁 {day_num}"
            return " 🔁 monthly"

        return " 🔁"

    def _build_list_item(self, ev: Event, *, now: datetime) -> ListItem:
        main = self._format_row(ev)
        notes_block = _format_event_notes_block(ev.notes or [])
        notes_w = Static(notes_block, classes="event_row_notes", markup=False)
        if notes_block:
            notes_w.add_class("is-visible")

        # Repeat indicator
        repeat_text = self._format_repeat_text(ev)
        repeat_w = Static(repeat_text, markup=False, classes="event_repeat")

        row = Container(
            Horizontal(
                Static(self._event_notify_glyph(ev), classes="event_notify", markup=False),
                Label(main, classes="event_row_main", markup=True),
                repeat_w,
                classes="event_row_main_line",
            ),
            notes_w,
            classes="event_row",
        )
        self._apply_temporal_classes(row, ev, now=now)

        return ListItem(row)

    def _fmt_day_friendly(self, day: date, today: date) -> str:
        return fmt_day_compact_friendly(day, today=today)

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

            # Update repeat indicator
            repeat_text = self._format_repeat_text(updated)
            item.query_one(".event_repeat", Static).update(repeat_text)

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
        # Create a sorted copy to find new position
        sorted_events = sorted(self._events, key=lambda ev: event_list_sort_key(ev, today=today_local()))
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
            repeat=None,
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
                # Assign repeat field if provided
                if result.repeat:
                    ev.repeat = result.repeat
                    self._repo.upsert_event(ev)
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
            repeat=ev.repeat,
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
                # Update repeat field separately
                updated.repeat = result.repeat
                self._repo.upsert_event(updated)
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
        """Cycle through repeat frequencies (none → daily → weekly → monthly)."""
        ev = self._selected_event()
        if ev is None:
            return

        try:
            from logui.usecases import cycle_event_repeat

            updated = cycle_event_repeat(self._repo, ev.id)
            self._update_selected_item_in_place(updated)

            # Show current frequency
            freq = "ninguna"
            if updated.repeat and isinstance(updated.repeat, dict):
                f = updated.repeat.get("freq", "none")
                if f == "daily":
                    freq = "diaria"
                elif f == "weekly":
                    freq = "semanal"
                elif f == "monthly":
                    freq = "mensual"

            self._notify(f"Repetición: {freq}")
        except Exception as e:  # noqa: BLE001
            self._notify(f"Error: {e}")

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


def _fmt_time(t: time | None) -> str:
    return t.strftime("%H:%M") if t else ""
