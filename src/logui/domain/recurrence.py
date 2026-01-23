"""Recurrence calculation logic for events and tasks."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any


def occurs_on_date(base_date: date, repeat: dict[str, Any] | None, target: date) -> bool:
    """Check if a recurring item has an occurrence on the target date.
    
    Args:
        base_date: The original/first occurrence date
        repeat: Recurrence configuration (freq, interval, until, count)
        target: Date to check for an occurrence
    
    Returns:
        True if there's an occurrence on target date, False otherwise
    """
    if repeat is None or not isinstance(repeat, dict):
        return base_date == target
    
    freq = repeat.get("freq")
    if not freq or freq == "none":
        return base_date == target
    
    # Can't occur before the base date
    if target < base_date:
        return False
    
    # Check "until" constraint
    until_str = repeat.get("until")
    if until_str:
        try:
            until = date.fromisoformat(until_str) if isinstance(until_str, str) else until_str
            if target > until:
                return False
        except (ValueError, TypeError):
            pass
    
    interval = int(repeat.get("interval", 1))
    if interval < 1:
        interval = 1
    
    delta = (target - base_date).days
    
    if freq == "daily":
        return delta % interval == 0
    
    elif freq == "weekly":
        weeks_diff = delta // 7
        return delta % 7 == 0 and weeks_diff % interval == 0
    
    elif freq == "monthly":
        # Monthly: same day of month, N months apart
        months_diff = (target.year - base_date.year) * 12 + (target.month - base_date.month)
        return target.day == base_date.day and months_diff % interval == 0
    
    return False


def next_occurrence(
    base_date: date,
    repeat: dict[str, Any] | None,
    after: date,
) -> date | None:
    """Calculate the next occurrence after a given date.
    
    Args:
        base_date: The original/first occurrence date
        repeat: Recurrence configuration
        after: Find the next occurrence after this date
    
    Returns:
        Next occurrence date, or None if no more occurrences
    """
    if repeat is None or not isinstance(repeat, dict):
        return None
    
    freq = repeat.get("freq")
    if not freq or freq == "none":
        return None
    
    interval = int(repeat.get("interval", 1))
    if interval < 1:
        interval = 1
    
    # Check "until" constraint
    until: date | None = None
    until_str = repeat.get("until")
    if until_str:
        try:
            until = date.fromisoformat(until_str) if isinstance(until_str, str) else until_str
        except (ValueError, TypeError):
            pass
    
    # Start searching from the day after "after"
    candidate = after + timedelta(days=1)
    
    # Avoid infinite loops: limit search to 5 years
    max_date = after + timedelta(days=365 * 5)
    
    while candidate <= max_date:
        if until and candidate > until:
            return None
        
        if occurs_on_date(base_date, repeat, candidate):
            return candidate
        
        # Move to next day (brute force but simple and correct)
        candidate += timedelta(days=1)
    
    return None


def list_occurrences(
    base_date: date,
    repeat: dict[str, Any] | None,
    start: date,
    end: date,
    max_count: int = 100,
) -> list[date]:
    """List all occurrences within a date range.
    
    Args:
        base_date: The original/first occurrence date
        repeat: Recurrence configuration
        start: Range start (inclusive)
        end: Range end (inclusive)
        max_count: Maximum number of occurrences to return
    
    Returns:
        List of occurrence dates within the range
    """
    if repeat is None or not isinstance(repeat, dict):
        if start <= base_date <= end:
            return [base_date]
        return []
    
    freq = repeat.get("freq")
    if not freq or freq == "none":
        if start <= base_date <= end:
            return [base_date]
        return []
    
    occurrences: list[date] = []
    current = max(base_date, start)
    
    while current <= end and len(occurrences) < max_count:
        if occurs_on_date(base_date, repeat, current):
            occurrences.append(current)
        
        # Move to next day
        current += timedelta(days=1)
    
    return occurrences
