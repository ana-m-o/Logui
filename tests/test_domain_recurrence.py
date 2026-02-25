"""Tests for event recurrence functionality."""

from __future__ import annotations

from datetime import date

from logui.domain.recurrence import list_occurrences, next_occurrence, occurs_on_date


def test_occurs_on_date_no_repeat() -> None:
    """Event without repeat only occurs on its base date."""
    base = date(2026, 1, 15)
    assert occurs_on_date(base, None, base) is True
    assert occurs_on_date(base, None, date(2026, 1, 16)) is False
    assert occurs_on_date(base, {"freq": "none"}, base) is True
    assert occurs_on_date(base, {"freq": "none"}, date(2026, 1, 16)) is False


def test_occurs_on_date_daily() -> None:
    """Daily repeat occurs every day."""
    base = date(2026, 1, 15)
    repeat = {"freq": "daily", "interval": 1}

    assert occurs_on_date(base, repeat, date(2026, 1, 15)) is True
    assert occurs_on_date(base, repeat, date(2026, 1, 16)) is True
    assert occurs_on_date(base, repeat, date(2026, 1, 20)) is True
    assert occurs_on_date(base, repeat, date(2026, 1, 14)) is False  # before base


def test_occurs_on_date_daily_with_interval() -> None:
    """Daily repeat with interval=2 occurs every 2 days."""
    base = date(2026, 1, 15)
    repeat = {"freq": "daily", "interval": 2}

    assert occurs_on_date(base, repeat, date(2026, 1, 15)) is True
    assert occurs_on_date(base, repeat, date(2026, 1, 16)) is False
    assert occurs_on_date(base, repeat, date(2026, 1, 17)) is True
    assert occurs_on_date(base, repeat, date(2026, 1, 19)) is True
    assert occurs_on_date(base, repeat, date(2026, 1, 21)) is True


def test_occurs_on_date_weekly() -> None:
    """Weekly repeat occurs every 7 days."""
    base = date(2026, 1, 15)  # Thursday
    repeat = {"freq": "weekly", "interval": 1}

    assert occurs_on_date(base, repeat, date(2026, 1, 15)) is True
    assert occurs_on_date(base, repeat, date(2026, 1, 22)) is True  # next Thursday
    assert occurs_on_date(base, repeat, date(2026, 1, 29)) is True
    assert occurs_on_date(base, repeat, date(2026, 1, 16)) is False  # Friday


def test_occurs_on_date_monthly() -> None:
    """Monthly repeat occurs on same day of month."""
    base = date(2026, 1, 15)
    repeat = {"freq": "monthly", "interval": 1}

    assert occurs_on_date(base, repeat, date(2026, 1, 15)) is True
    assert occurs_on_date(base, repeat, date(2026, 2, 15)) is True
    assert occurs_on_date(base, repeat, date(2026, 3, 15)) is True
    assert occurs_on_date(base, repeat, date(2026, 2, 16)) is False


def test_occurs_on_date_with_until() -> None:
    """Repeat with 'until' stops after that date."""
    base = date(2026, 1, 15)
    repeat = {"freq": "daily", "interval": 1, "until": "2026-01-20"}

    assert occurs_on_date(base, repeat, date(2026, 1, 15)) is True
    assert occurs_on_date(base, repeat, date(2026, 1, 20)) is True
    assert occurs_on_date(base, repeat, date(2026, 1, 21)) is False  # after until


def test_next_occurrence_daily() -> None:
    """Next occurrence for daily repeat."""
    base = date(2026, 1, 15)
    repeat = {"freq": "daily", "interval": 1}

    assert next_occurrence(base, repeat, date(2026, 1, 15)) == date(2026, 1, 16)
    assert next_occurrence(base, repeat, date(2026, 1, 20)) == date(2026, 1, 21)


def test_next_occurrence_weekly() -> None:
    """Next occurrence for weekly repeat."""
    base = date(2026, 1, 15)  # Thursday
    repeat = {"freq": "weekly", "interval": 1}

    assert next_occurrence(base, repeat, date(2026, 1, 15)) == date(2026, 1, 22)
    assert next_occurrence(base, repeat, date(2026, 1, 20)) == date(2026, 1, 22)


def test_next_occurrence_none_when_until_passed() -> None:
    """Next occurrence returns None when until date is passed."""
    base = date(2026, 1, 15)
    repeat = {"freq": "daily", "interval": 1, "until": "2026-01-20"}

    assert next_occurrence(base, repeat, date(2026, 1, 20)) is None
    assert next_occurrence(base, repeat, date(2026, 1, 25)) is None


def test_list_occurrences_daily() -> None:
    """List occurrences for daily repeat in a range."""
    base = date(2026, 1, 15)
    repeat = {"freq": "daily", "interval": 1}

    occurrences = list_occurrences(base, repeat, date(2026, 1, 15), date(2026, 1, 20))
    assert len(occurrences) == 6
    assert occurrences[0] == date(2026, 1, 15)
    assert occurrences[-1] == date(2026, 1, 20)


def test_list_occurrences_weekly() -> None:
    """List occurrences for weekly repeat in a range."""
    base = date(2026, 1, 15)  # Thursday
    repeat = {"freq": "weekly", "interval": 1}

    occurrences = list_occurrences(base, repeat, date(2026, 1, 15), date(2026, 2, 15))
    assert len(occurrences) == 5  # Jan 15, 22, 29, Feb 5, 12
    assert occurrences[0] == date(2026, 1, 15)
    assert occurrences[1] == date(2026, 1, 22)


def test_list_occurrences_no_repeat() -> None:
    """List occurrences for non-repeating event."""
    base = date(2026, 1, 15)

    occurrences = list_occurrences(base, None, date(2026, 1, 10), date(2026, 1, 20))
    assert occurrences == [date(2026, 1, 15)]

    occurrences = list_occurrences(base, None, date(2026, 1, 16), date(2026, 1, 20))
    assert occurrences == []
