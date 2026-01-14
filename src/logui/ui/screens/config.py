from __future__ import annotations

from dataclasses import dataclass

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView, Static

from logui.domain.entities.config import AppConfig
from logui.domain.ports.config import ConfigRepository
from logui.usecases.config import (
    set_all_day_notify_time,
    set_default_notify_minutes_before,
    update_editor,
)


@dataclass(frozen=True)
class EditorFormResult:
    command: str
    args_text: str


class EditorConfigScreen(ModalScreen[EditorFormResult | None]):
    BINDINGS = [
        Binding("enter", "submit", "Save", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, *, initial_command: str, initial_args_text: str):
        super().__init__()
        self._initial_command = initial_command
        self._initial_args_text = initial_args_text
        self.add_class("modal")

    def compose(self) -> ComposeResult:
        yield Container(
            Label("External editor", classes="modal_title"),
            Static(
                "enter save • esc cancel",
                classes="modal_help",
                markup=False,
            ),
            Label("Command"),
            Input(value=self._initial_command, id="editor_command"),
            Label("Args (optional)"),
            Input(
                value=self._initial_args_text,
                id="editor_args",
                placeholder="e.g.: --wait {file}  (if you don't add {file}, it's appended)",
            ),
            Static(
                "Suggestions: vim, nvim, nano, emacs, code\n"
                "Note: fallback is nano if command is empty",
                classes="modal_help_top",
                markup=False,
            ),
            id="editor_config",
            classes="modal_box modal_w80",
        )

    def action_submit(self) -> None:
        cmd = self.query_one("#editor_command", Input).value
        args = self.query_one("#editor_args", Input).value
        self.dismiss(EditorFormResult(command=cmd, args_text=args))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_submit()

    def action_cancel(self) -> None:
        self.dismiss(None)


@dataclass(frozen=True)
class TextFormResult:
    value: str


class SimpleTextInputScreen(ModalScreen[TextFormResult | None]):
    BINDINGS = [
        Binding("enter", "submit", "Save", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, *, title: str, label: str, initial: str, placeholder: str = ""):
        super().__init__()
        self._title = title
        self._label = label
        self._initial = initial
        self._placeholder = placeholder
        self.add_class("modal")

    def compose(self) -> ComposeResult:
        yield Container(
            Label(self._title, classes="modal_title"),
            Static("enter save • esc cancel", classes="modal_help", markup=False),
            Label(self._label),
            Input(value=self._initial, id="value", placeholder=self._placeholder),
            id="simple_text_input",
            classes="modal_box modal_w60",
        )

    def action_submit(self) -> None:
        val = self.query_one("#value", Input).value
        self.dismiss(TextFormResult(value=val))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_submit()

    def action_cancel(self) -> None:
        self.dismiss(None)


class _ConfigRow(ListItem):
    def __init__(self, *, key: str, title: str, value: str):
        super().__init__()
        self.key = key
        self._title = title
        self._value = value

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Label(self._title),
            Static(self._value, classes="config_value", markup=False),
            classes="config_row",
        )


class ConfigPane(Container):
    BINDINGS = [
        Binding("enter", "edit", "Edit", show=False, priority=True),
        Binding("e", "edit", "Edit", show=False, priority=True),
    ]

    def __init__(self, repo: ConfigRepository, *, data_dir_text: str):
        super().__init__(id="config")
        self._repo = repo
        self._data_dir_text = data_dir_text
        self._config: AppConfig = AppConfig.default()

    def compose(self) -> ComposeResult:
        help_text = (
            "  ↑/↓ select option • enter/e edit\n"
        )

        yield Container(
            Horizontal(Label("Config / Help"), classes="page_header"),
            Static(help_text, classes="page_help", markup=False),
            VerticalScroll(
                Static(f"Data directory: {self._data_dir_text}", markup=False),
                Label("Configuration"),
                ListView(id="config_list"),
                Label("Help"),
                Static(
                    "- No system notifications: all is in-app (toast + sound).\n"
                    "- In modals: enter confirm • esc cancel.",
                    markup=False,
                ),
                classes="page_scroll",
            ),
        )

    def on_mount(self) -> None:
        self._refresh()
        self.call_later(self._focus_list)

    def _focus_list(self) -> None:
        try:
            lv = self.query_one("#config_list", ListView)
            if len(list(lv.query(ListItem))) > 0:
                lv.index = 0
            lv.focus()
        except Exception:  # noqa: BLE001
            pass

    def _notify(self, message: str) -> None:
        notify = getattr(self.app, "notify", None)
        if callable(notify):
            notify(message)

    def _refresh(self) -> None:
        self._config = self._repo.load()

        editor_cmd = (self._config.editor.command or "nano").strip() or "nano"
        args = self._config.editor.normalized_args()
        args_text = " ".join(args) if args else "(no args)"
        all_day = (self._config.notifications.all_day_notify_time or "09:00").strip() or "09:00"
        default_mins = int(self._config.notifications.default_minutes_before)

        lv = self.query_one("#config_list", ListView)
        lv.clear()
        lv.append(_ConfigRow(key="editor", title="Editor", value=f"{editor_cmd}  {args_text}"))
        lv.append(
            _ConfigRow(key="all_day_notify_time", title="All-day notify time", value=all_day)
        )
        lv.append(
            _ConfigRow(
                key="default_notify_minutes",
                title="Default notify minutes",
                value=str(default_mins),
            )
        )

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

        if getattr(list_view, "id", None) != "config_list":
            return

        list_view.focus()
        self.call_later(self.action_edit)

    def _selected_key(self) -> str | None:
        try:
            lv = self.query_one("#config_list", ListView)
            item = lv.highlighted_child
        except Exception:  # noqa: BLE001
            return None
        if isinstance(item, _ConfigRow):
            return item.key
        return None

    def action_edit(self) -> None:
        key = self._selected_key()
        if not key:
            return

        if key == "editor":
            editor_cmd = (self._config.editor.command or "nano").strip() or "nano"
            args_text = " ".join(self._config.editor.normalized_args())

            def _on_done(res: EditorFormResult | None) -> None:
                if res is None:
                    return
                update_editor(repo=self._repo, command=res.command, args_text=res.args_text)
                self._notify("Editor updated")
                self.call_later(self._refresh)

            self.app.push_screen(
                EditorConfigScreen(initial_command=editor_cmd, initial_args_text=args_text),
                callback=_on_done,
            )
            return


        if key == "all_day_notify_time":
            initial = (self._config.notifications.all_day_notify_time or "09:00").strip() or "09:00"

            def _on_done(res: TextFormResult | None) -> None:
                if res is None:
                    return
                before = self._config.notifications.all_day_notify_time
                set_all_day_notify_time(repo=self._repo, hhmm=res.value)
                self.call_later(self._refresh)
                after_reload = self._repo.load()
                if after_reload.notifications.all_day_notify_time != before:
                    self._notify("All-day notification time updated")
                else:
                    self._notify("Invalid format. Use HH:MM (e.g.: 09:00)")

            self.app.push_screen(
                SimpleTextInputScreen(
                    title="All-day event notification",
                    label="Time (HH:MM)",
                    initial=initial,
                    placeholder="09:00",
                ),
                callback=_on_done,
            )
            return

        if key == "default_notify_minutes":
            initial = str(int(self._config.notifications.default_minutes_before))

            def _on_done(res: TextFormResult | None) -> None:
                if res is None:
                    return
                s = (res.value or "").strip()
                try:
                    mins = int(s)
                except Exception:  # noqa: BLE001
                    self._notify("Invalid value. Use a number (e.g.: 0, 10, 15)")
                    return
                if mins < 0:
                    mins = 0
                set_default_notify_minutes_before(repo=self._repo, minutes=mins)
                self._notify("Default minutes updated")
                self.call_later(self._refresh)

            self.app.push_screen(
                SimpleTextInputScreen(
                    title="Timed event notification",
                    label="Minutes before (0 = at event time)",
                    initial=initial,
                    placeholder="0",
                ),
                callback=_on_done,
            )
            return
