from __future__ import annotations

from datetime import date

from logui.ui.screens.tasks import _build_due_date_hint_text


def test_due_date_hint_shows_friendly_date_and_type() -> None:
    txt = _build_due_date_hint_text(
        due_date_raw="25/12/2025",
        today=date(2025, 12, 25),
    )
    assert "25 Dec, 2025" in txt


def test_due_date_hint_shows_past_date_note() -> None:
    txt = _build_due_date_hint_text(
        due_date_raw="24/12/2025",
        today=date(2025, 12, 25),
    )
    assert "(is a past date)" in txt
