from __future__ import annotations

from datetime import date

from logui.ui.screens.events import _build_end_day_hint_text, _build_start_day_hint_text


def test_start_hint_empty_date_empty_time_shows_hoy_todo_el_dia():
    today = date(2025, 12, 25)
    assert (
        _build_start_day_hint_text(
            start_day_raw="",
            start_time_raw="",
            initial_start_day=today,
            today=today,
        )
        == "[dim]Today, 2025 (all day)[/dim]"
    )


def test_start_hint_date_no_time_shows_day_with_year_todo_el_dia():
    today = date(2025, 12, 25)
    assert (
        _build_start_day_hint_text(
            start_day_raw="4/3/26",
            start_time_raw="",
            initial_start_day=today,
            today=today,
        )
        == "[dim]4 Mar, 2026 (all day)[/dim]"
    )


def test_start_hint_date_and_time_includes_time():
    today = date(2025, 12, 25)
    assert (
        _build_start_day_hint_text(
            start_day_raw="",
            start_time_raw="20:30",
            initial_start_day=today,
            today=today,
        )
        == "[dim]Today, 2025 20:30[/dim]"
    )


def test_end_hint_hidden_for_single_day_all_day():
    today = date(2025, 12, 25)
    assert (
        _build_end_day_hint_text(
            start_day_raw="",
            end_day_raw="",
            start_time_raw="",
            end_time_raw="",
            initial_start_day=today,
            today=today,
        )
        == ""
    )


def test_end_hint_all_day_multi_day_shows_end_date_and_todo_el_dia():
    today = date(2025, 12, 25)
    assert (
        _build_end_day_hint_text(
            start_day_raw="28/12/2025",
            end_day_raw="30/1/26",
            start_time_raw="",
            end_time_raw="",
            initial_start_day=today,
            today=today,
        )
        == "[dim]30 Jan, 2026 (all day)[/dim]"
    )


def test_end_hint_timed_with_end_time_shows_end_date_and_time():
    today = date(2025, 12, 25)
    assert (
        _build_end_day_hint_text(
            start_day_raw="28/12/2025",
            end_day_raw="3/1/26",
            start_time_raw="20:30",
            end_time_raw="15:00",
            initial_start_day=today,
            today=today,
        )
        == "[dim]3 Jan, 2026 15:00[/dim]"
    )


def test_end_hint_timed_without_end_time_defaults_plus_1h_and_marks_default():
    today = date(2025, 12, 25)
    assert (
        _build_end_day_hint_text(
            start_day_raw="",
            end_day_raw="",
            start_time_raw="10:00",
            end_time_raw="",
            initial_start_day=today,
            today=today,
        )
        == "[dim]25 Dec, 2025 11:00 (default +1h)[/dim]"
    )


def test_end_hint_timed_default_plus_1h_rollover_updates_end_day():
    today = date(2025, 12, 25)
    assert (
        _build_end_day_hint_text(
            start_day_raw="",
            end_day_raw="",
            start_time_raw="23:30",
            end_time_raw="",
            initial_start_day=today,
            today=today,
        )
        == "[dim]26 Dec, 2025 00:30 (default +1h)[/dim]"
    )
