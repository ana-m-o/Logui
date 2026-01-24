"""Tests for monthly recurrence with days that don't exist in all months."""

from datetime import date

from logui.domain.recurrence import occurs_on_date, next_occurrence


def test_monthly_recurrence_day_31_to_february():
    """Event on day 31 should occur on last day of February (28/29)."""
    base = date(2026, 1, 31)  # Saturday, January 31
    repeat = {"freq": "monthly", "interval": 1}
    
    # February 2026 has 28 days (not a leap year)
    assert occurs_on_date(base, repeat, date(2026, 2, 28)) is True
    assert occurs_on_date(base, repeat, date(2026, 2, 27)) is False
    assert occurs_on_date(base, repeat, date(2026, 2, 1)) is False
    
    # March has 31 days, so it should occur on day 31
    assert occurs_on_date(base, repeat, date(2026, 3, 31)) is True
    assert occurs_on_date(base, repeat, date(2026, 3, 30)) is False


def test_monthly_recurrence_day_31_leap_year():
    """Event on day 31 in leap year February should occur on Feb 29."""
    base = date(2024, 1, 31)  # January 31, 2024
    repeat = {"freq": "monthly", "interval": 1}
    
    # February 2024 has 29 days (leap year)
    assert occurs_on_date(base, repeat, date(2024, 2, 29)) is True
    assert occurs_on_date(base, repeat, date(2024, 2, 28)) is False


def test_monthly_recurrence_day_30_to_february():
    """Event on day 30 should occur on last day of February."""
    base = date(2026, 1, 30)
    repeat = {"freq": "monthly", "interval": 1}
    
    # February 2026 has 28 days
    assert occurs_on_date(base, repeat, date(2026, 2, 28)) is True
    assert occurs_on_date(base, repeat, date(2026, 2, 27)) is False
    
    # March has 30+ days, so it should occur on day 30
    assert occurs_on_date(base, repeat, date(2026, 3, 30)) is True


def test_monthly_recurrence_day_31_to_april():
    """Event on day 31 should occur on April 30 (last day)."""
    base = date(2026, 1, 31)
    repeat = {"freq": "monthly", "interval": 1}
    
    # April has 30 days
    assert occurs_on_date(base, repeat, date(2026, 4, 30)) is True
    assert occurs_on_date(base, repeat, date(2026, 4, 29)) is False
    
    # May has 31 days
    assert occurs_on_date(base, repeat, date(2026, 5, 31)) is True


def test_monthly_recurrence_day_15_normal():
    """Event on day 15 should always occur on day 15 (exists in all months)."""
    base = date(2026, 1, 15)
    repeat = {"freq": "monthly", "interval": 1}
    
    assert occurs_on_date(base, repeat, date(2026, 2, 15)) is True
    assert occurs_on_date(base, repeat, date(2026, 3, 15)) is True
    assert occurs_on_date(base, repeat, date(2026, 4, 15)) is True
    assert occurs_on_date(base, repeat, date(2026, 2, 14)) is False
    assert occurs_on_date(base, repeat, date(2026, 2, 16)) is False


def test_next_occurrence_monthly_day_31():
    """next_occurrence should correctly handle day 31 across months."""
    base = date(2026, 1, 31)
    repeat = {"freq": "monthly", "interval": 1}
    
    # Next after January 31 should be February 28
    next_date = next_occurrence(base, repeat, after=base)
    assert next_date == date(2026, 2, 28)
    
    # Next after February 28 should be March 31
    next_date = next_occurrence(base, repeat, after=date(2026, 2, 28))
    assert next_date == date(2026, 3, 31)
    
    # Next after March 31 should be April 30
    next_date = next_occurrence(base, repeat, after=date(2026, 3, 31))
    assert next_date == date(2026, 4, 30)
    
    # Next after April 30 should be May 31
    next_date = next_occurrence(base, repeat, after=date(2026, 4, 30))
    assert next_date == date(2026, 5, 31)


def test_next_occurrence_monthly_day_29():
    """Day 29 should occur on Feb 28 in non-leap years."""
    base = date(2026, 1, 29)
    repeat = {"freq": "monthly", "interval": 1}
    
    # February 2026 has 28 days (not leap year)
    next_date = next_occurrence(base, repeat, after=base)
    assert next_date == date(2026, 2, 28)


def test_monthly_interval_2_with_day_31():
    """Every 2 months with day 31 should skip months without day 31 or use last day."""
    base = date(2026, 1, 31)
    repeat = {"freq": "monthly", "interval": 2}
    
    # Should NOT occur in February (interval=2 means skip)
    assert occurs_on_date(base, repeat, date(2026, 2, 28)) is False
    
    # Should occur in March (2 months after January)
    assert occurs_on_date(base, repeat, date(2026, 3, 31)) is True
    
    # Should NOT occur in April
    assert occurs_on_date(base, repeat, date(2026, 4, 30)) is False
    
    # Should occur in May (4 months after January)
    assert occurs_on_date(base, repeat, date(2026, 5, 31)) is True


def test_monthly_recurrence_preserves_exact_day_when_possible():
    """When the day exists in target month, must match exactly (not last day)."""
    base = date(2026, 1, 31)
    repeat = {"freq": "monthly", "interval": 1}
    
    # In months with 31 days, must be day 31, not day 30
    assert occurs_on_date(base, repeat, date(2026, 3, 31)) is True
    assert occurs_on_date(base, repeat, date(2026, 3, 30)) is False
    
    # In months with 30 days, must be day 30 (last day)
    assert occurs_on_date(base, repeat, date(2026, 4, 30)) is True
    assert occurs_on_date(base, repeat, date(2026, 4, 29)) is False
