"""Refactored Journal screen following Textual best practices."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView, Static, TextArea

from logui.domain.errors import ValidationError
from logui.domain.ports.journal import JournalRepository
from logui.ui.dates import fmt_day_header_en, fmt_day_list_short_en
from logui.ui.parsing import parse_date_flexible, today_local
from logui.ui.screens.modals import ConfirmScreen

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class JournalEditorResult:
    day: date
    text: str


class JournalEditorScreen(ModalScreen[JournalEditorResult | None]):
    BINDINGS = [
        Binding("ctrl+shift+s", "submit", "Save", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, repo: JournalRepository, *, initial_day: date, initial_text: str):
        super().__init__()
        self._repo = repo
        self._initial_day = initial_day
        self._initial_text = initial_text
        self._active_day = initial_day
        self.add_class("modal")

    def compose(self) -> ComposeResult:
        yield Container(
            Label(
                f"Journal — {fmt_day_header_en(self._initial_day)}",
                id="journal_editor_title",
                classes="modal_title",
            ),
            Static("[dim]ctrl+shift+s save • esc cancel[/dim]", classes="modal_help"),
            Label("Date *"),
            Input(
                value=self._initial_day.isoformat(),
                placeholder="2025-12-29, 29/12/2025, 5/7, 25 (default today)",
                id="journal_day",
            ),
            Label("Text"),
            TextArea(text=self._initial_text or "", id="journal_text"),
            Static("", id="journal_editor_error", classes="modal_error"),
            id="journal_editor",
            classes="modal_box modal_w80 modal_h1fr",
        )

    def on_mount(self) -> None:
        try:
            self.query_one("#journal_text", TextArea).focus()
        except Exception:  # noqa: BLE001
            self.query_one("#journal_day", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        self._submit()

    @on(Input.Submitted, "#journal_day")
    def on_day_input_submitted(self, event: Input.Submitted) -> None:
        self._load_day_from_input(load_even_if_missing=True)

    @on(Input.Changed, "#journal_day")
    def on_day_input_changed(self, event: Input.Changed) -> None:
        day_raw = (event.value or "").strip()
        if not day_raw:
            return
        parsed_day = self._parse_day_input(day_raw)
        if parsed_day is None:
            return
        title = self.query_one("#journal_editor_title", Label)
        title.update(f"Journal — {fmt_day_header_en(parsed_day)}")

    def _parse_day_input(self, value: str) -> date | None:
        try:
            return parse_date_flexible(value, today=today_local())
        except Exception:  # noqa: BLE001
            return None

    def _load_day_from_input(self, *, load_even_if_missing: bool) -> None:
        day_raw = (self.query_one("#journal_day", Input).value or "").strip()
        if not day_raw:
            return

        parsed_day = self._parse_day_input(day_raw)
        if parsed_day is None or parsed_day == self._active_day:
            return

        text = self._safe_get_entry_text(parsed_day)
        if not text.strip() and not load_even_if_missing:
            return

        self._active_day = parsed_day
        self.query_one("#journal_text", TextArea).text = text

    def _safe_get_entry_text(self, day: date) -> str:
        try:
            return self._repo.get_entry(day) or ""
        except Exception:  # noqa: BLE001
            return ""

    def _set_error(self, message: str, *, input_widget: Input | None = None) -> None:
        error = self.query_one("#journal_editor_error", Static)
        error.update(message)
        if input_widget is not None:
            input_widget.add_class("error")

    def _clear_errors(self) -> None:
        self.query_one("#journal_editor_error", Static).update("")
        for input_widget in self.query(Input):
            input_widget.remove_class("error")

    def _submit(self) -> None:
        self._clear_errors()

        journal_day_input = self.query_one("#journal_day", Input)
        day_raw = (journal_day_input.value or "").strip()
        if not day_raw:
            self._set_error("[red]• Date cannot be empty[/red]", input_widget=journal_day_input)
            return

        parsed_day = self._parse_day_input(day_raw)
        if parsed_day is None:
            self._set_error(
                "[red]• Invalid date. Allowed formats: YYYY-MM-DD (2025-12-29), "
                "DD/MM/YYYY (29/12/2025), DD/MM (5/7), DD/MM/YY (3/6/26), "
                "MM-DD (12-25) o DD (25).[/red]",
                input_widget=journal_day_input,
            )
            return

        try:
            text = self.query_one("#journal_text", TextArea).text
        except Exception:  # noqa: BLE001
            text = ""

        self.dismiss(JournalEditorResult(day=parsed_day, text=text))


class JournalDayItem(ListItem):
    def __init__(self, day: date):
        super().__init__()
        self.day = day

    def compose(self) -> ComposeResult:
        yield Static(fmt_day_list_short_en(self.day), markup=False)


class JournalPane(Container):
    BINDINGS = [
        Binding("n", "new", "New", show=False),
        Binding("enter", "edit", "Edit", show=False, priority=True),
        Binding("e", "edit", "Edit", show=False, priority=True),
        Binding("x", "delete", "Delete", show=False),
    ]

    selected_day: reactive[date | None] = reactive(None, init=False)

    def __init__(self, repo: JournalRepository):
        super().__init__(id="journal")
        self._repo = repo
        self._entry_days: list[date] = []
        # Backward-compat for tests/legacy callers
        self._days_with_entries: list[date] = []
        self._suppress_highlighted = False
        self._pending_selected_day: date | None = None

    def compose(self) -> ComposeResult:
        yield Container(
            Horizontal(Label("Journal"), classes="page_header"),
            Static(
                "[dim]↑/↓ history • n new • e/enter edit • x delete[/dim]",
                classes="page_help",
            ),
            Horizontal(
                Container(
                    Label("Entries", classes="journal_section_title"),
                    ListView(id="journal_history_list", classes="journal_history"),
                    id="journal_left",
                ),
                Container(
                    Label("", id="journal_detail_title", classes="journal_detail_title"),
                    VerticalScroll(
                        Static("", id="journal_detail_text", markup=False),
                        id="journal_detail_scroll",
                        classes="journal_detail_scroll",
                    ),
                    id="journal_right",
                ),
                id="journal_layout",
            ),
        )

    def on_mount(self) -> None:
        self._refresh_entries(select_first=True)
        self._list_view().focus()

    def _list_view(self) -> ListView:
        return self.query_one("#journal_history_list", ListView)

    def _detail_title(self) -> Label:
        return self.query_one("#journal_detail_title", Label)

    def _detail_text(self) -> Static:
        return self.query_one("#journal_detail_text", Static)

    def _fetch_entry_days(self) -> list[date]:
        try:
            return list(self._repo.list_entry_days())
        except Exception as e:  # noqa: BLE001
            _log.warning("Failed listing journal days: %s", e)
            return []

    def _render_entry_list(self, days: list[date]) -> None:
        lv = self._list_view()
        lv.clear()
        for day in days:
            lv.append(JournalDayItem(day))

    def _refresh_entries(self, *, select_first: bool) -> None:
        self._entry_days = self._fetch_entry_days()
        self._days_with_entries = list(self._entry_days)
        self._render_entry_list(self._entry_days)
        if select_first and self._entry_days and len(self._list_view().children) > 0:
            self._set_list_index(0, set_selected_day=True)

    def _set_list_index(self, index: int, *, set_selected_day: bool) -> None:
        lv = self._list_view()
        lv.index = index
        if set_selected_day and 0 <= index < len(self._entry_days):
            self.selected_day = self._entry_days[index]
        if 0 <= index < len(lv.children):
            lv.scroll_to_widget(lv.children[index])

    def _select_day_in_list(self, target_day: date) -> None:
        for i, day in enumerate(self._entry_days):
            if day == target_day:
                lv = self._list_view()
                lv.index = None
                self._set_list_index(i, set_selected_day=True)
                return
        if self._entry_days and len(self._list_view().children) > 0:
            self._set_list_index(0, set_selected_day=True)

    @on(ListView.Highlighted, "#journal_history_list")
    def on_list_highlighted(self, event: ListView.Highlighted) -> None:
        if self._suppress_highlighted:
            return

        new_day = event.item.day if isinstance(event.item, JournalDayItem) else None
        if self._pending_selected_day is not None and new_day != self._pending_selected_day:
            return
        if self._pending_selected_day is not None:
            self._pending_selected_day = None

        self.selected_day = new_day

    def watch_selected_day(self, new_day: date | None) -> None:
        if new_day is None:
            self._render_empty_state()
        else:
            self._render_entry_detail(new_day)

    def _render_entry_detail(self, day: date) -> None:
        self._detail_title().update(f"{fmt_day_header_en(day)}")
        text = self._safe_get_entry_text(day)
        if text.strip():
            self._detail_text().update(text)
        else:
            self._detail_text().update("(No entry) — press n or enter to write")

    def _render_empty_state(self) -> None:
        self._detail_title().update("No selection")
        self._detail_text().update("(No entries)")

    @on(events.Click, "#journal_right, #journal_detail_scroll, #journal_detail_text")
    def on_detail_clicked(self, event: events.Click) -> None:
        self._list_view().focus()

    @on(events.Click, ".journal_history")
    def on_history_double_click(self, event: events.Click) -> None:
        if event.button == 1 and event.chain >= 2:
            self.action_edit()

    def action_new(self) -> None:
        today = today_local()
        self._open_editor(initial_day=today, initial_text=self._safe_get_entry_text(today))

    def action_edit(self) -> None:
        if self.selected_day is None:
            return
        self._open_editor(
            initial_day=self.selected_day,
            initial_text=self._safe_get_entry_text(self.selected_day),
        )

    def action_delete(self) -> None:
        if self.selected_day is None:
            return
        self._confirm_delete(self.selected_day)

    def _open_editor(self, *, initial_day: date, initial_text: str) -> None:
        def _on_save(result: JournalEditorResult | None) -> None:
            if result is None:
                return
            if not result.text.strip():
                self._confirm_delete(result.day)
                return
            self._save_entry(result.day, result.text)

        self.app.push_screen(
            JournalEditorScreen(self._repo, initial_day=initial_day, initial_text=initial_text),
            callback=_on_save,
        )

    def _save_entry(self, day: date, text: str) -> None:
        try:
            self._repo.set_entry(day, text)
        except ValidationError as e:
            self.app.notify(f"Error: {e}", severity="error")
            return
        except Exception as e:  # noqa: BLE001
            _log.error("Failed to save journal entry: %s", e)
            self.app.notify("Error saving entry", severity="error")
            return

        self.app.notify("Entry saved", severity="information")
        self._reload_and_select(day)

    def _confirm_delete(self, day: date) -> None:
        text = self._safe_get_entry_text(day)
        if not text.strip():
            self.app.notify("No entry to delete", severity="warning")
            return

        def _on_confirm(confirmed: bool) -> None:
            if not confirmed:
                return
            try:
                self._repo.delete_entry(day)
            except Exception as e:  # noqa: BLE001
                _log.error("Failed to delete journal entry: %s", e)
                self.app.notify("Error deleting entry", severity="error")
                return

            self.app.notify("Entry deleted", severity="information")
            self._reload_and_select(None)

        self.app.push_screen(ConfirmScreen("Delete this journal entry?"), callback=_on_confirm)

    def _reload_and_select(self, target_day: date | None) -> None:
        if target_day is not None:
            self._pending_selected_day = target_day
            self._suppress_highlighted = True
            self._refresh_entries(select_first=False)
            self._suppress_highlighted = False
            self._select_day_in_list(target_day)
        else:
            self._pending_selected_day = None
            self._refresh_entries(select_first=True)
            try:
                self._list_view().focus()
            except Exception:  # noqa: BLE001
                pass

    def _safe_get_entry_text(self, day: date) -> str:
        try:
            return self._repo.get_entry(day) or ""
        except Exception as e:  # noqa: BLE001
            _log.warning("Failed loading journal entry for %s: %s", day, e)
            return ""
