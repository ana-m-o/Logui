"""Utilidades de formateo de fechas para la UI.

Note: we centralize formatting here to avoid duplicating month/day maps.
"""

from __future__ import annotations

from datetime import date

_EN_MONTHS_SHORT: dict[int, str] = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dec",
}

_EN_WEEKDAYS_SHORT: dict[int, str] = {
    0: "Mon",
    1: "Tue",
    2: "Wed",
    3: "Thu",
    4: "Fri",
    5: "Sat",
    6: "Sun",
}


def fmt_day_full_friendly(day: date) -> str:
    """Fixed format with year: `29 Dec, 2026`."""
    return f"{day.day} {_EN_MONTHS_SHORT.get(day.month, str(day.month))}, {day.year}"


def fmt_day_short_friendly(day: date, *, today: date) -> str:
    """Short format (maintaining current behavior): `29 Dec, 2026`."""
    base = f"{day.day} {_EN_MONTHS_SHORT.get(day.month, str(day.month))}"
    return f"{base}, {day.year}"


def fmt_day_compact_friendly(day: date, *, today: date) -> str:
    """Compact format with weekday: `Wed 26 Feb` (without year if it's the current year).

    Special cases:
    - Today: `[bold]Today[/bold] - Wed 25 Feb`
    - Tomorrow: `[bold]Tomorrow[/bold] - Thu 26 Feb`
    
    If the year is later than `today`, includes the year.
    """
    from datetime import timedelta
    
    wd = _EN_WEEKDAYS_SHORT.get(day.weekday(), str(day.weekday()))
    base = f"{wd} {day.day} {_EN_MONTHS_SHORT.get(day.month, str(day.month))}"
    if day.year > today.year:
        base = f"{base}, {day.year}"
    
    # Check if it's today or tomorrow
    if day == today:
        return f"[bold]Today[/bold] - {base}"
    elif day == today + timedelta(days=1):
        return f"[bold]Tomorrow[/bold] - {base}"
    
    return base


def fmt_day_header_en(day: date) -> str:
    """English header format: `Mon 29 Dec, 2026` (used by Journal)."""
    wd = _EN_WEEKDAYS_SHORT.get(day.weekday(), str(day.weekday()))
    mon = _EN_MONTHS_SHORT.get(day.month, str(day.month))
    return f"{wd} {day.day} {mon}, {day.year}"


def fmt_day_list_short_en(day: date) -> str:
    """Short English list format: `29 Dec 2026` (used by Journal)."""
    mon = _EN_MONTHS_SHORT.get(day.month, str(day.month))
    return f"{day.day} {mon} {day.year}"
