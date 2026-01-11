from __future__ import annotations

from datetime import date, datetime, time, timedelta

from logui.domain.entities.event import Event
from logui.usecases.event_notifications import (
    DEFAULT_ALL_DAY_NOTIFY_TIME,
    DEFAULT_GRACE,
    due_at_for_event,
    due_notifications,
)


def _mk_event(
    *,
    title: str,
    day: date,
    start: time | None,
    notify: bool = True,
    minutes_before: int | None = None,
) -> Event:
    return Event.create(
        title,
        day=day,
        start_time=start,
        end_time=None,
        notify=notify,
        notify_minutes_before=minutes_before,
    )


def test_due_at_for_all_day_uses_default_time() -> None:
    ev = _mk_event(title="All day", day=date(2025, 12, 26), start=None, notify=True)
    due = due_at_for_event(ev)
    assert due == datetime.combine(date(2025, 12, 26), DEFAULT_ALL_DAY_NOTIFY_TIME)


def test_due_at_for_timed_uses_minutes_before_default_0() -> None:
    ev = _mk_event(
        title="Meet",
        day=date(2025, 12, 26),
        start=time(9, 30),
        notify=True,
        minutes_before=None,
    )
    due = due_at_for_event(ev, default_minutes_before=0)
    assert due == datetime(2025, 12, 26, 9, 30)


def test_due_at_for_timed_subtracts_minutes_before() -> None:
    ev = _mk_event(
        title="Dentist",
        day=date(2025, 12, 26),
        start=time(10, 0),
        notify=True,
        minutes_before=15,
    )
    due = due_at_for_event(ev)
    assert due == datetime(2025, 12, 26, 9, 45)


def test_due_notifications_fires_within_grace_once() -> None:
    ev = _mk_event(title="Meet", day=date(2025, 12, 26), start=time(10, 0), notify=True)
    now = datetime(2025, 12, 26, 10, 0) + timedelta(seconds=30)

    sent: set[str] = set()
    due1 = due_notifications([ev], now=now, already_sent=sent, grace=DEFAULT_GRACE)
    assert [d.title for d in due1] == ["Meet"]

    # Mark as sent and ensure it doesn't fire again.
    sent.add(f"{ev.id}:{due1[0].due_at.isoformat()}")
    due2 = due_notifications([ev], now=now, already_sent=sent, grace=DEFAULT_GRACE)
    assert due2 == []


def test_due_notifications_does_not_fire_before_due() -> None:
    ev = _mk_event(
        title="Soon",
        day=date(2025, 12, 26),
        start=time(10, 0),
        notify=True,
        minutes_before=10,
    )
    # due at 09:50
    now = datetime(2025, 12, 26, 9, 49, 59)
    due = due_notifications([ev], now=now, already_sent=set(), grace=DEFAULT_GRACE)
    assert due == []
