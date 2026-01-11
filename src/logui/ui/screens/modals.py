from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Static


class ConfirmScreen(ModalScreen[bool]):
    BINDINGS = [
        Binding("y", "yes", "Yes", show=False),
        Binding("n", "no", "No", show=False),
        Binding("enter", "yes", "Yes", show=False),
        Binding("escape", "no", "No", show=False),
    ]

    def __init__(self, message: str):
        super().__init__()
        self._message = message
        self.add_class("modal")

    def compose(self) -> ComposeResult:
        yield Container(
            Static(self._message, id="confirm_message"),
            Static(
                "[dim]enter = yes • esc = no • y/n[/dim]",
                id="confirm_help",
                classes="modal_help_top",
            ),
            id="confirm",
            classes="modal_box modal_w60",
        )

    def action_yes(self) -> None:
        self.dismiss(True)

    def action_no(self) -> None:
        self.dismiss(False)

