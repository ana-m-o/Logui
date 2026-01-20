from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView, Static, TextArea

from logui.domain.errors import ValidationError
from logui.domain.ports.journal import JournalRepository
from logui.ui.dates import fmt_day_header_en, fmt_day_list_short_en
from logui.ui.parsing import parse_date_flexible, today_local
from logui.ui.screens.modals import ConfirmScreen


def fmt_day_header_friendly(day: date) -> str:
    return fmt_day_header_en(day)


def fmt_day_list_short(day: date) -> str:
    return fmt_day_list_short_en(day)


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
                f"Journal — {fmt_day_header_friendly(self._initial_day)}",
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

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "journal_day":
            return
        self._load_day_from_input(load_even_if_missing=True)

    def on_input_blurred(self, event: Input.Blurred) -> None:
        if event.input.id != "journal_day":
            return
        self._load_day_from_input(load_even_if_missing=True)

    def _load_day_from_input(self, *, load_even_if_missing: bool) -> None:
        day_raw = (self.query_one("#journal_day", Input).value or "").strip()
        if not day_raw:
            return

        try:
            parsed_day = parse_date_flexible(day_raw, today=today_local())
        except Exception:  # noqa: BLE001
            return

        if parsed_day == self._active_day:
            return

        title = self.query_one("#journal_editor_title", Label)
        title.update(f"Journal — {fmt_day_header_friendly(parsed_day)}")

        text = ""
        try:
            existing = self._repo.get_entry(parsed_day)
        except Exception:  # noqa: BLE001
            existing = None

        if existing is not None and (existing or "").strip():
            text = existing
        elif load_even_if_missing:
            text = ""
        else:
            return

        self._active_day = parsed_day
        self.query_one("#journal_text", TextArea).text = text

    def _submit(self) -> None:
        error = self.query_one("#journal_editor_error", Static)
        error.update("")

        # Clear all error classes first
        for input_widget in self.query(Input):
            input_widget.remove_class("error")

        journal_day_input = self.query_one("#journal_day", Input)
        day_raw = (journal_day_input.value or "").strip()
        
        if not day_raw:
            journal_day_input.add_class("error")
            error.update("[red]• Date cannot be empty[/red]")
            return

        try:
            parsed_day = parse_date_flexible(day_raw, today=today_local())
        except Exception:  # noqa: BLE001
            journal_day_input.add_class("error")
            error.update(
                "[red]• Invalid date. Allowed formats: YYYY-MM-DD (2025-12-29), "
                "DD/MM/YYYY (29/12/2025), DD/MM (5/7), DD/MM/YY (3/6/26), "
                "MM-DD (12-25) o DD (25).[/red]"
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
        yield Static(fmt_day_list_short(self.day), markup=False)


class JournalPane(Container):
    BINDINGS = [
        Binding("n", "new", "New", show=False),
        Binding("enter", "edit", "Edit", show=False, priority=True),
        Binding("e", "edit", "Edit", show=False, priority=True),
        Binding("x", "delete", "Delete", show=False),
        Binding("[", "prev_day", "Prev day", show=False),
        Binding("]", "next_day", "Next day", show=False),
        Binding(".", "today", "Today", show=False),
    ]

    def __init__(self, repo: JournalRepository):
        super().__init__(id="journal")
        self._repo = repo
        self._selected_day: date = today_local()
        self._days_with_entries: list[date] = []

    def compose(self) -> ComposeResult:
        yield Container(
            Horizontal(Label("Journal"), classes="page_header"),
            Static(
                "[dim]↑/↓ history • n new • e/enter edit • x delete • / day • . today[/dim]",
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
        self._refresh()
        self._disable_detail_focus()
        try:
            self.query_one("#journal_history_list", ListView).focus()
        except Exception:  # noqa: BLE001
            pass

    def _disable_detail_focus(self) -> None:
        # The right-side detail view is read-only; keep keyboard focus on the list.
        for selector in (
            "#journal_right",
            "#journal_detail_title",
            "#journal_detail_scroll",
            "#journal_detail_text",
        ):
            try:
                w = self.query_one(selector)
                setattr(w, "can_focus", False)
                setattr(w, "can_focus_children", False)
            except Exception:  # noqa: BLE001
                pass

    def _notify(self, message: str) -> None:
        notify = getattr(self.app, "notify", None)
        if callable(notify):
            notify(message)

    def _refresh(self) -> None:
        try:
            self._days_with_entries = list(self._repo.list_entry_days())
        except Exception:  # noqa: BLE001
            self._days_with_entries = []

        lv = self.query_one("#journal_history_list", ListView)
        lv.clear()

        for d in self._days_with_entries:
            lv.append(JournalDayItem(d))

        # Try to select the current day if it exists in the list.
        idx = None
        for i, d in enumerate(self._days_with_entries):
            if d == self._selected_day:
                idx = i
                break
        if idx is not None:
            lv.index = idx

        self._render_detail()
        self._disable_detail_focus()

    def _render_detail(self) -> None:
        title = self.query_one("#journal_detail_title", Label)
        title.update(f"{fmt_day_header_friendly(self._selected_day)}")

        text_widget = self.query_one("#journal_detail_text", Static)
        text = None
        try:
            text = self._repo.get_entry(self._selected_day)
        except Exception:  # noqa: BLE001
            text = None

        if text is None or not (text or "").strip():
            text_widget.update("(No entry) — press n or enter to write")
        else:
            text_widget.update(text)

    def _day_from_history_list(self) -> date | None:
        try:
            lv = self.query_one("#journal_history_list", ListView)
        except Exception:  # noqa: BLE001
            return None

        idx = lv.index
        if idx is None:
            idx = 0

        try:
            children = list(lv.children)
        except Exception:  # noqa: BLE001
            return None

        if idx < 0 or idx >= len(children):
            return None

        item = children[idx]
        if isinstance(item, JournalDayItem):
            return item.day
        return None

    def _sync_selected_day_from_history_list(self) -> None:
        day = self._day_from_history_list()
        if day is None or day == self._selected_day:
            return
        self._selected_day = day
        self._render_detail()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id != "journal_history_list":
            return
        if isinstance(event.item, JournalDayItem):
            self._selected_day = event.item.day
            self._render_detail()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.id != "journal_history_list":
            return
        if isinstance(event.item, JournalDayItem):
            if event.item.day != self._selected_day:
                self._selected_day = event.item.day
                self._render_detail()

    def on_click(self, event: events.Click) -> None:
        # If the user clicks in the read-only detail view, keep focus on the list.
        w = event.widget
        while w is not None:
            widget_id = getattr(w, "id", None)
            if widget_id in {"journal_right", "journal_detail_scroll", "journal_detail_text"}:
                try:
                    self.query_one("#journal_history_list", ListView).focus()
                except Exception:  # noqa: BLE001
                    pass
                return
            w = getattr(w, "parent", None)

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

        if getattr(list_view, "id", None) != "journal_history_list":
            return

        list_view.focus()
        self.call_later(self.action_edit)

    def _has_entry(self, day: date) -> bool:
        try:
            txt = self._repo.get_entry(day)
        except Exception:  # noqa: BLE001
            return False
        return bool((txt or "").strip())

    def action_prev_day(self) -> None:
        self._selected_day = self._selected_day.fromordinal(self._selected_day.toordinal() - 1)
        self._render_detail()

    def action_next_day(self) -> None:
        self._selected_day = self._selected_day.fromordinal(self._selected_day.toordinal() + 1)
        self._render_detail()

    def action_today(self) -> None:
        self._selected_day = today_local()
        self._render_detail()

    def action_new(self) -> None:
        self._selected_day = today_local()
        self._refresh()
        self.action_edit()

    def action_edit(self) -> None:
        self._sync_selected_day_from_history_list()
        initial_text = self._repo.get_entry(self._selected_day) or ""
        original_day = self._selected_day

        def _save(result: JournalEditorResult | None) -> None:
            if result is None:
                return

            target_day = result.day
            text = result.text or ""

            # Empty = deletion, but confirm.
            if not text.strip():
                self._confirm_delete(target_day)
                return

            self._apply_save(target_day=target_day, text=text)

        self.app.push_screen(
            JournalEditorScreen(self._repo, initial_day=original_day, initial_text=initial_text),
            callback=_save,
        )

    def _apply_save(self, *, target_day: date, text: str) -> None:
        try:
            self._repo.set_entry(target_day, text)
        except ValidationError as e:
            self._notify(f"Error: {e}")
            return
        except Exception:  # noqa: BLE001
            self._notify("Error saving the entry")
            return

        self._selected_day = target_day
        self._notify("Entry saved")
        self._refresh()

    def _confirm_delete(self, day: date) -> None:
        if not self._has_entry(day):
            self._notify("No entry to delete")
            return

        def _on_confirm(ok: bool) -> None:
            if not ok:
                return
            try:
                self._repo.delete_entry(day)
            except Exception:  # noqa: BLE001
                self._notify("Error deleting the entry")
                return
            self._notify("Entry deleted")
            self._refresh()

        self.app.push_screen(ConfirmScreen("Delete entry for the day?"), callback=_on_confirm)

    def action_delete(self) -> None:
        self._sync_selected_day_from_history_list()
        self._confirm_delete(self._selected_day)
