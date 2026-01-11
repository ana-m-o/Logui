from __future__ import annotations

from datetime import date, datetime, time, timezone

import pytest

from logui.domain.entities.event import Event
from logui.domain.errors import ValidationError


def test_event_create_requires_title() -> None:
    with pytest.raises(ValidationError):
        Event.create("", day=date(2025, 1, 1))


def test_event_end_time_requires_start_time() -> None:
    with pytest.raises(ValidationError):
        Event.create(
            "Title",
            day=date(2025, 1, 1),
            end_time=time(10, 0),
        )


def test_event_end_before_start_rejected_same_day() -> None:
    with pytest.raises(ValidationError):
        Event.create(
            "Title",
            day=date(2025, 1, 1),
            start_time=time(10, 0),
            end_time=time(9, 0),
            end_day_offset=0,
        )


def test_event_end_before_start_allowed_next_day() -> None:
    ev = Event.create(
        "Title",
        day=date(2025, 1, 1),
        start_time=time(23, 0),
        end_time=time(1, 0),
        end_day_offset=1,
    )
    assert ev.end_day_offset == 1


def test_event_all_day_can_span_multiple_days() -> None:
    ev = Event.create(
        "Trip",
        day=date(2025, 12, 28),
        start_time=None,
        end_time=None,
        end_day_offset=33,
    )
    assert ev.end_day_offset == 33


def test_event_timed_can_span_multiple_days() -> None:
    ev = Event.create(
        "Conference",
        day=date(2025, 12, 28),
        start_time=time(20, 30),
        end_time=time(15, 0),
        end_day_offset=6,
    )
    assert ev.end_day_offset == 6


def test_event_to_from_dict_roundtrip() -> None:
    now = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    ev = Event.create(
        "Dentist",
        day=date(2025, 1, 2),
        now=now,
        start_time=time(9, 30),
        end_time=time(10, 0),
        notify=True,
        notify_minutes_before=0,
        repeat={"freq": "weekly", "interval": 1},
    )
    ev.add_note("Bring papers", now=now)

    data = ev.to_dict()
    ev2 = Event.from_dict(data)

    assert ev2.id == ev.id
    assert ev2.title == "Dentist"
    assert ev2.date == date(2025, 1, 2)
    assert ev2.start_time == time(9, 30)
    assert ev2.end_time == time(10, 0)
    assert ev2.end_day_offset == 0
    assert ev2.notify is True
    assert ev2.notify_minutes_before == 0
    assert ev2.repeat == {"freq": "weekly", "interval": 1}
    assert len(ev2.notes) == 1
    assert ev2.notes[0].text == "Bring papers"


def test_event_rejects_negative_notify_minutes_before() -> None:
    with pytest.raises(ValidationError):
        Event.create(
            "Title",
            day=date(2025, 1, 1),
            notify_minutes_before=-1,
        )
