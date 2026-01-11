from __future__ import annotations

from logui.domain.entities.event import EventNote
from logui.ui.screens.events import _format_event_notes_block


def test_format_event_notes_block_bullets_and_newlines() -> None:
    n1 = EventNote.create("Nota 1")
    n2 = EventNote.create("Nota 2")

    assert _format_event_notes_block([n1, n2]) == "- Nota 1\n- Nota 2"


def test_format_event_notes_block_ignores_empty_lines() -> None:
    n1 = EventNote.create("Nota 1")

    # EventNote itself won't allow empty text, but the formatter should be defensive.
    broken = EventNote(id=n1.id, text="   ", created_at=n1.created_at)

    assert _format_event_notes_block([broken, n1]) == "- Nota 1"
