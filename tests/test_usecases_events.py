from __future__ import annotations

from datetime import date, time
from pathlib import Path
from uuid import uuid4

import pytest

from logui.domain.errors import ValidationError
from logui.infrastructure.persistence.sqlite_database import SQLiteDatabase
from logui.infrastructure.repositories.events_repo_sqlite import SqliteEventRepository
from logui.usecases.events import (
    CreateEventInput,
    UpdateEventPatch,
    create_event,
    cycle_event_repeat,
    list_events_for_date,
    toggle_event_notify,
    update_event,
)


def test_list_events_for_date_orders_all_day_first_then_time(tmp_path: Path) -> None:
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteEventRepository(db)
    day = date(2025, 12, 25)

    all_day = create_event(
        repo,
        CreateEventInput(title="All day", day=day, start_time=None),
    )
    morning = create_event(
        repo,
        CreateEventInput(title="Morning", day=day, start_time=time(9, 0)),
    )
    afternoon = create_event(
        repo,
        CreateEventInput(title="Afternoon", day=day, start_time=time(15, 0)),
    )

    ordered = list_events_for_date(repo, day)
    assert [e.id for e in ordered] == [all_day.id, morning.id, afternoon.id]


def test_create_event_defaults_end_time_plus_1h(tmp_path: Path) -> None:
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteEventRepository(db)
    ev = create_event(
        repo,
        CreateEventInput(
            title="Meet",
            day=date(2025, 12, 25),
            start_time=time(10, 0),
            end_time=None,
        ),
    )
    assert ev.end_time == time(11, 0)
    assert ev.end_day_offset == 0


def test_create_event_defaults_end_time_crosses_midnight(tmp_path: Path) -> None:
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteEventRepository(db)
    ev = create_event(
        repo,
        CreateEventInput(
            title="Late",
            day=date(2025, 12, 25),
            start_time=time(23, 30),
            end_time=None,
        ),
    )
    assert ev.end_time == time(0, 30)
    assert ev.end_day_offset == 1


def test_create_event_sets_default_notify_minutes_before_when_missing(tmp_path: Path) -> None:
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteEventRepository(db)
    ev = create_event(
        repo,
        CreateEventInput(
            title="Dentist",
            day=date(2025, 12, 25),
            start_time=time(9, 30),
            notify=True,
            notify_minutes_before=None,
        ),
        default_notify_minutes_before=0,
    )
    assert ev.notify is True
    assert ev.notify_minutes_before == 0


def test_toggle_notify_sets_default_minutes_when_enabling(tmp_path: Path) -> None:
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteEventRepository(db)
    ev = create_event(
        repo,
        CreateEventInput(
            title="Dentist",
            day=date(2025, 12, 25),
            start_time=time(9, 30),
            notify=False,
            notify_minutes_before=None,
        ),
    )

    updated = toggle_event_notify(repo, ev.id, default_notify_minutes_before=0)
    assert updated.notify is True
    assert updated.notify_minutes_before == 0


def test_cycle_repeat_cycles_and_saves_freq_only(tmp_path: Path) -> None:
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteEventRepository(db)
    ev = create_event(repo, CreateEventInput(title="R", day=date(2025, 12, 25)))

    ev1 = cycle_event_repeat(repo, ev.id)
    assert ev1.repeat == {"freq": "daily"}

    ev2 = cycle_event_repeat(repo, ev.id)
    assert ev2.repeat == {"freq": "weekly"}


def test_update_start_time_preserves_duration_when_end_not_provided(tmp_path: Path) -> None:
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteEventRepository(db)
    ev = create_event(
        repo,
        CreateEventInput(
            title="Meet",
            day=date(2025, 12, 25),
            start_time=time(10, 0),
            end_time=time(11, 30),
            end_day_offset=0,
        ),
    )

    updated = update_event(repo, ev.id, UpdateEventPatch(start_time=time(9, 0)))
    assert updated.start_time == time(9, 0)
    assert updated.end_time == time(10, 30)
    assert updated.end_day_offset == 0


def test_update_start_time_preserves_duration_across_multiple_days(tmp_path: Path) -> None:
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteEventRepository(db)
    ev = create_event(
        repo,
        CreateEventInput(
            title="Long",
            day=date(2025, 12, 28),
            start_time=time(20, 30),
            end_time=time(15, 0),
            end_day_offset=6,
        ),
    )

    # Move start time by +1 hour; duration should remain the same.
    updated = update_event(repo, ev.id, UpdateEventPatch(start_time=time(21, 30)))
    assert updated.start_time == time(21, 30)
    assert updated.end_time == time(16, 0)
    assert updated.end_day_offset == 6


def test_update_event_missing_raises(tmp_path: Path) -> None:
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteEventRepository(db)
    with pytest.raises(ValidationError):
        update_event(repo, uuid4(), UpdateEventPatch())


def test_update_clearing_start_time_clears_end_time(tmp_path: Path) -> None:
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteEventRepository(db)
    ev = create_event(
        repo,
        CreateEventInput(
            title="Meet",
            day=date(2025, 12, 25),
            start_time=time(10, 0),
            end_time=time(11, 0),
            end_day_offset=0,
        ),
    )

    updated = update_event(repo, ev.id, UpdateEventPatch(start_time=None))
    assert updated.start_time is None
    assert updated.end_time is None
