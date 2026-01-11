from __future__ import annotations

from datetime import date

from logui.ui.screens.events import parse_date_flexible


def test_parse_date_flexible_accepts_dd_mm_yy():
    today = date(2025, 12, 25)
    assert parse_date_flexible("3/6/26", today=today) == date(2026, 6, 3)


def test_parse_date_flexible_accepts_dd_mm_defaults_year():
    today = date(2025, 12, 25)
    # Next occurrence: 2025-07-05 already passed, so use next year.
    assert parse_date_flexible("5/7", today=today) == date(2026, 7, 5)


def test_parse_date_flexible_dd_uses_next_month_when_past_in_current_month() -> None:
    today = date(2025, 12, 26)
    assert parse_date_flexible("3", today=today) == date(2026, 1, 3)


def test_parse_date_flexible_dd_mm_uses_current_year_when_future() -> None:
    today = date(2025, 1, 1)
    assert parse_date_flexible("3/1", today=today) == date(2025, 1, 3)


def test_parse_date_flexible_dd_mm_uses_next_year_when_past() -> None:
    today = date(2025, 1, 26)
    assert parse_date_flexible("3/1", today=today) == date(2026, 1, 3)
