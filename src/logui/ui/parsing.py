"""Shared parsing helpers for the UI.

These functions used to live in the Events screen module, but they are
consumed by multiple screens (Tasks, Journal, etc.). Keeping them here avoids
cross-screen imports and reduces coupling.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time

from logui.domain.errors import ValidationError


def today_local() -> date:
    return datetime.now().date()


def parse_time_flexible(raw: str) -> time:
    s = (raw or "").strip()
    if not s:
        raise ValidationError("time is empty")
    if ":" not in s:
        s = f"{s}:00"
    try:
        hh_s, mm_s = s.split(":", 1)
        hh = int(hh_s)
        mm = int(mm_s)
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError("out of range")
        return time(hh, mm)
    except (TypeError, ValueError) as e:
        raise ValidationError("Invalid time") from e


def parse_date_flexible(raw: str, *, today: date) -> date:
    s = (raw or "").strip()
    if not s:
        raise ValidationError("date is empty")

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue

    def _add_months(year: int, month: int, *, add: int) -> tuple[int, int]:
        total = (year * 12) + (month - 1) + add
        new_year = total // 12
        new_month = (total % 12) + 1
        return new_year, new_month

    # DD/MM -> next occurrence (if already passed this year, use next year)
    m = re.fullmatch(r"\s*(\d{1,2})/(\d{1,2})\s*", s)
    if m:
        day = int(m.group(1))
        month = int(m.group(2))
        try:
            cand = date(today.year, month, day)
        except ValueError as e:
            raise ValidationError("Invalid date") from e

        if cand < today:
            try:
                return date(today.year + 1, month, day)
            except ValueError as e:
                raise ValidationError("Invalid date") from e
        return cand

    # MM-DD -> next occurrence (if already passed this year, use next year)
    m = re.fullmatch(r"\s*(\d{1,2})-(\d{1,2})\s*", s)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        try:
            cand = date(today.year, month, day)
        except ValueError as e:
            raise ValidationError("Invalid date") from e

        if cand < today:
            try:
                return date(today.year + 1, month, day)
            except ValueError as e:
                raise ValidationError("Invalid date") from e
        return cand

    # DD -> next occurrence (if already passed this month, use next month)
    m = re.fullmatch(r"\s*(\d{1,2})\s*", s)
    if m:
        day = int(m.group(1))

        start_add = 0 if day >= today.day else 1
        for add in range(start_add, 24):
            y, mo = _add_months(today.year, today.month, add=add)
            try:
                cand = date(y, mo, day)
            except ValueError:
                continue
            if cand >= today:
                return cand

        raise ValidationError("Invalid date")

    raise ValidationError("Invalid date")
