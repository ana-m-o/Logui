from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.widget import Widget


class TitledBox(Widget):
    def __init__(
        self,
        title: str,
        *,
        child: Widget,
        subtitle: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(id=id, classes=classes)
        self._title = title
        self._child = child
        self.border_title = title
        if subtitle:
            self.border_subtitle = subtitle

    def compose(self) -> ComposeResult:
        yield Container(self._child, classes="titled_box__body")
