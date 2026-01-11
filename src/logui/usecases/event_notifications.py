from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from uuid import UUID

from logui.domain.entities.event import Event

DEFAULT_ALL_DAY_NOTIFY_TIME = time(9, 0)
DEFAULT_GRACE = timedelta(minutes=5)


@dataclass(frozen=True)
class EventNotification:
    event_id: UUID
    due_at: datetime
    title: str
    minutes_before: int | None


def due_at_for_event(
    ev: Event,
    *,
    default_minutes_before: int = 0,
    all_day_notify_time: time = DEFAULT_ALL_DAY_NOTIFY_TIME,
) -> datetime | None:
    """Compute when an event notification should fire (local naive datetime).

    Rules (MVP):
    - If notify is off: no notification.
    - Timed events notify at start_time minus notify_minutes_before (default 0).
    - All-day events notify at all_day_notify_time on the event date.

    Note: repeat rules are not expanded in MVP; event.date is the only occurrence.
    """

    if not ev.notify:
        return None

    if ev.start_time is None:
        return datetime.combine(ev.date, all_day_notify_time)

    minutes_before = ev.notify_minutes_before
    if minutes_before is None:
        minutes_before = default_minutes_before

    start_dt = datetime.combine(ev.date, ev.start_time)
    return start_dt - timedelta(minutes=int(minutes_before))


def notification_key(event_id: UUID, due_at: datetime) -> str:
    return f"{event_id}:{due_at.isoformat()}"


def due_notifications(
    events: list[Event],
    *,
    now: datetime,
    already_sent: set[str],
    grace: timedelta = DEFAULT_GRACE,
    default_minutes_before: int = 0,
    all_day_notify_time: time = DEFAULT_ALL_DAY_NOTIFY_TIME,
) -> list[EventNotification]:
    """Return notifications that should fire at 'now' (once per key)."""

    due: list[EventNotification] = []
    for ev in events:
        due_at = due_at_for_event(
            ev,
            default_minutes_before=default_minutes_before,
            all_day_notify_time=all_day_notify_time,
        )
        if due_at is None:
            continue

        minutes_before: int | None = None
        if ev.start_time is not None:
            mb = ev.notify_minutes_before
            if mb is None:
                mb = default_minutes_before
            minutes_before = int(mb)

        key = notification_key(ev.id, due_at)
        if key in already_sent:
            continue

        if due_at <= now < (due_at + grace):
            due.append(
                EventNotification(
                    event_id=ev.id,
                    due_at=due_at,
                    title=ev.title,
                    minutes_before=minutes_before,
                )
            )

    # Stable ordering (useful for tests)
    due.sort(key=lambda n: (n.due_at, str(n.event_id)))
    return due
