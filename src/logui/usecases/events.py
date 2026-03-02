from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any
from uuid import UUID

from logui.domain.entities.event import Event, EventNote
from logui.domain.errors import ValidationError
from logui.domain.ports.events import EventRepository


@dataclass(frozen=True)
class CreateEventInput:
    title: str
    day: date
    start_time: time | None = None
    end_time: time | None = None
    end_day_offset: int = 0
    notify: bool = True
    notify_minutes_before: int | None = None
    repeat: dict[str, Any] | None = None


_MISSING = object()


@dataclass(frozen=True)
class UpdateEventPatch:
    title: str | object = _MISSING
    day: date | object = _MISSING
    start_time: time | None | object = _MISSING
    end_time: time | None | object = _MISSING
    end_day_offset: int | object = _MISSING
    notify: bool | object = _MISSING
    notify_minutes_before: int | None | object = _MISSING
    repeat: dict[str, Any] | None | object = _MISSING


_REPEAT_CYCLE = ["none", "daily", "weekly", "monthly"]


def list_events_for_date(repo: EventRepository, day: date) -> list[Event]:
    """List all events for a given date, including recurring occurrences."""
    # Include events that occur on this day (base date or recurring occurrence)
    events = [e for e in repo.list_events() if e.occurs_on(day)]

    def sort_key(ev: Event) -> tuple[int, int, str]:
        # all-day first
        all_day_rank = 0 if ev.start_time is None else 1
        minutes = -1
        if ev.start_time is not None:
            minutes = ev.start_time.hour * 60 + ev.start_time.minute
        return (all_day_rank, minutes, str(ev.id))

    events.sort(key=sort_key)
    return events


def create_event(
    repo: EventRepository,
    data: CreateEventInput,
    *,
    now: datetime | None = None,
    default_notify_minutes_before: int = 0,
) -> Event:
    start_time = data.start_time
    end_time = data.end_time
    end_day_offset = data.end_day_offset

    if start_time is not None and end_time is None:
        end_time, end_day_offset = _default_end_time_plus_1h(start_time)

    notify_minutes_before = data.notify_minutes_before
    if data.notify and start_time is not None and notify_minutes_before is None:
        notify_minutes_before = default_notify_minutes_before

    ev = Event.create(
        data.title,
        day=data.day,
        now=now,
        start_time=start_time,
        end_time=end_time,
        end_day_offset=end_day_offset,
        notify=data.notify,
        notify_minutes_before=notify_minutes_before,
        repeat=data.repeat,
    )
    repo.upsert_event(ev)
    return ev


def update_event(
    repo: EventRepository,
    event_id: UUID,
    patch: UpdateEventPatch,
    *,
    now: datetime | None = None,
    default_notify_minutes_before: int = 0,
) -> Event:
    existing = repo.get_event(event_id)
    if existing is None:
        raise ValidationError("Event not found")

    title = existing.title if patch.title is _MISSING else str(patch.title)
    day = existing.date if patch.day is _MISSING else patch.day

    start_time = existing.start_time if patch.start_time is _MISSING else patch.start_time
    end_time = existing.end_time if patch.end_time is _MISSING else patch.end_time
    end_day_offset = (
        existing.end_day_offset if patch.end_day_offset is _MISSING else int(patch.end_day_offset)
    )

    # If user clears start_time, end_time must also be cleared unless explicitly provided.
    if patch.start_time is not _MISSING and start_time is None and patch.end_time is _MISSING:
        end_time = None

    # Preserve duration when only start_time changes.
    if (
        patch.start_time is not _MISSING
        and patch.end_time is _MISSING
        and existing.start_time is not None
        and existing.end_time is not None
    ):
        duration_minutes = _duration_minutes(
            existing.start_time, existing.end_time, existing.end_day_offset
        )
        if start_time is not None:
            end_time, end_day_offset = _add_minutes_to_time(start_time, duration_minutes)

    # Default end_time if start_time has value and end_time is missing.
    if start_time is not None and end_time is None:
        end_time, end_day_offset = _default_end_time_plus_1h(start_time)

    notify = existing.notify if patch.notify is _MISSING else bool(patch.notify)
    notify_minutes_before = (
        existing.notify_minutes_before
        if patch.notify_minutes_before is _MISSING
        else patch.notify_minutes_before
    )

    repeat = existing.repeat if patch.repeat is _MISSING else patch.repeat

    if notify and start_time is not None and notify_minutes_before is None:
        notify_minutes_before = default_notify_minutes_before

    updated = Event(
        id=existing.id,
        title=title,
        date=day,
        start_time=start_time,
        end_time=end_time,
        end_day_offset=end_day_offset,
        notify=notify,
        notify_minutes_before=notify_minutes_before,
        repeat=repeat,
        notes=list(existing.notes),
        created_at=existing.created_at,
        updated_at=existing.updated_at,
    )
    updated._validate_all()  # noqa: SLF001
    updated.touch(now=now)

    repo.upsert_event(updated)
    return updated


def delete_event(repo: EventRepository, event_id: UUID) -> bool:
    return repo.delete_event(event_id)


def add_event_note(
    repo: EventRepository,
    event_id: UUID,
    text: str,
    *,
    now: datetime | None = None,
) -> Event:
    ev = repo.get_event(event_id)
    if ev is None:
        raise ValidationError("Event not found")
    ev.add_note(text, now=now)
    repo.upsert_event(ev)
    return ev


def update_event_note(
    repo: EventRepository,
    event_id: UUID,
    note_id: UUID,
    text: str,
    *,
    now: datetime | None = None,
) -> Event:
    ev = repo.get_event(event_id)
    if ev is None:
        raise ValidationError("Event not found")

    cleaned = (text or "").strip()
    if not cleaned:
        raise ValidationError("Note text cannot be empty")

    for idx, note in enumerate(ev.notes):
        if note.id == note_id:
            ev.notes[idx] = EventNote(id=note.id, text=cleaned, created_at=note.created_at)
            ev.touch(now=now)
            repo.upsert_event(ev)
            return ev

    raise ValidationError("Note not found")


def delete_event_note(
    repo: EventRepository,
    event_id: UUID,
    note_id: UUID,
    *,
    now: datetime | None = None,
) -> Event:
    ev = repo.get_event(event_id)
    if ev is None:
        raise ValidationError("Event not found")

    before = len(ev.notes)
    ev.notes = [n for n in ev.notes if n.id != note_id]
    if len(ev.notes) == before:
        raise ValidationError("Note not found")

    ev.touch(now=now)
    repo.upsert_event(ev)
    return ev


def move_event_note_up(
    repo: EventRepository,
    event_id: UUID,
    note_id: UUID,
    *,
    now: datetime | None = None,
) -> Event:
    """Move an event note up in the list (towards the beginning)."""
    return _move_event_note(repo, event_id, note_id, direction=-1, now=now)


def move_event_note_down(
    repo: EventRepository,
    event_id: UUID,
    note_id: UUID,
    *,
    now: datetime | None = None,
) -> Event:
    """Move an event note down in the list (towards the end)."""
    return _move_event_note(repo, event_id, note_id, direction=+1, now=now)


def _move_event_note(
    repo: EventRepository,
    event_id: UUID,
    note_id: UUID,
    *,
    direction: int,
    now: datetime | None = None,
) -> Event:
    """Move an event note up (-1) or down (+1) in the notes list."""
    if direction not in (-1, +1):
        raise ValueError("direction must be -1 or +1")

    ev = repo.get_event(event_id)
    if ev is None:
        raise ValidationError("Event not found")

    idx = next((i for i, n in enumerate(ev.notes) if n.id == note_id), None)
    if idx is None:
        raise ValidationError("Note not found")

    swap_idx = idx + direction
    if swap_idx < 0 or swap_idx >= len(ev.notes):
        # Already at boundary, no-op
        return ev

    # Swap the notes
    ev.notes[idx], ev.notes[swap_idx] = ev.notes[swap_idx], ev.notes[idx]

    ev.touch(now=now)
    repo.upsert_event(ev)
    return ev


def toggle_event_notify(
    repo: EventRepository,
    event_id: UUID,
    *,
    now: datetime | None = None,
    default_notify_minutes_before: int = 0,
) -> Event:
    ev = repo.get_event(event_id)
    if ev is None:
        raise ValidationError("Event not found")

    new_notify = not ev.notify
    new_minutes = ev.notify_minutes_before
    if new_notify and ev.start_time is not None and new_minutes is None:
        new_minutes = default_notify_minutes_before

    updated = Event(
        id=ev.id,
        title=ev.title,
        date=ev.date,
        start_time=ev.start_time,
        end_time=ev.end_time,
        end_day_offset=ev.end_day_offset,
        notify=new_notify,
        notify_minutes_before=new_minutes,
        repeat=ev.repeat,
        notes=list(ev.notes),
        created_at=ev.created_at,
        updated_at=ev.updated_at,
    )
    updated._validate_all()  # noqa: SLF001
    updated.touch(now=now)
    repo.upsert_event(updated)
    return updated


def cycle_event_repeat(
    repo: EventRepository,
    event_id: UUID,
    *,
    now: datetime | None = None,
) -> Event:
    ev = repo.get_event(event_id)
    if ev is None:
        raise ValidationError("Event not found")

    current = "none"
    if ev.repeat and isinstance(ev.repeat, dict) and ev.repeat.get("freq"):
        current = str(ev.repeat.get("freq"))

    try:
        idx = _REPEAT_CYCLE.index(current)
    except ValueError:
        idx = 0

    next_freq = _REPEAT_CYCLE[(idx + 1) % len(_REPEAT_CYCLE)]
    repeat = {"freq": next_freq}

    updated = Event(
        id=ev.id,
        title=ev.title,
        date=ev.date,
        start_time=ev.start_time,
        end_time=ev.end_time,
        end_day_offset=ev.end_day_offset,
        notify=ev.notify,
        notify_minutes_before=ev.notify_minutes_before,
        repeat=repeat,
        notes=list(ev.notes),
        created_at=ev.created_at,
        updated_at=ev.updated_at,
    )
    updated._validate_all()  # noqa: SLF001
    updated.touch(now=now)
    repo.upsert_event(updated)
    return updated


def _default_end_time_plus_1h(start_time: time) -> tuple[time, int]:
    return _add_minutes_to_time(start_time, 60)


def _add_minutes_to_time(t: time, minutes: int) -> tuple[time, int]:
    total = t.hour * 60 + t.minute + minutes
    if total < 0:
        raise ValidationError("Invalid negative time offset")

    day_offset = total // (24 * 60)
    total = total % (24 * 60)
    return time(total // 60, total % 60), int(day_offset)


def _duration_minutes(start: time, end: time, end_day_offset: int) -> int:
    start_min = start.hour * 60 + start.minute
    end_min = end.hour * 60 + end.minute + (end_day_offset * 24 * 60)
    return end_min - start_min


def process_recurring_events(
    repo: EventRepository,
    *,
    today: date,
    now: datetime | None = None,
) -> list[Event]:
    """Process recurring events that have passed and clone them for next occurrence.

    Returns list of newly created events.
    """
    new_events: list[Event] = []

    for event in repo.list_events():
        # Skip non-recurring events
        if not event.repeat or not isinstance(event.repeat, dict):
            continue

        freq = event.repeat.get("freq")
        if not freq or freq == "none":
            continue

        # Check if event has already passed
        event_end_date = event.date
        if event.end_day_offset and event.end_day_offset > 0:
            from datetime import timedelta

            event_end_date = event.date + timedelta(days=event.end_day_offset)

        # Only process events that have already passed
        if event_end_date >= today:
            continue

        # Find the next occurrence that is >= today
        next_date = event.next_occurrence(after=event_end_date)
        if next_date is None:
            continue

        # Keep advancing until we find a date >= today
        max_iterations = 365
        iteration = 0
        while next_date < today and iteration < max_iterations:
            next_date = event.next_occurrence(after=next_date)
            if next_date is None:
                break
            iteration += 1

        if next_date is None or next_date < today:
            continue

        # Create a new event for the next occurrence
        new_event = Event.create(
            title=event.title,
            day=next_date,
            now=now,
            start_time=event.start_time,
            end_time=event.end_time,
            end_day_offset=event.end_day_offset,
            notify=event.notify,
            notify_minutes_before=event.notify_minutes_before,
            repeat=dict(event.repeat),
        )
        # Notes are NOT cloned - they are unique to each occurrence
        repo.upsert_event(new_event)
        new_events.append(new_event)

        # Remove recurrence from original event (it's now a one-time past event)
        event.repeat = {"freq": "none"}
        event.touch(now=now)
        repo.upsert_event(event)

    return new_events
