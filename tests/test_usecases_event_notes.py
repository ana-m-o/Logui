from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from logui.domain.errors import ValidationError
from logui.infrastructure.persistence.sqlite_database import SQLiteDatabase
from logui.infrastructure.repositories.events_repo_sqlite import SqliteEventRepository
from logui.usecases.events import (
    CreateEventInput,
    add_event_note,
    create_event,
    delete_event_note,
    update_event_note,
)


def test_add_update_delete_event_note(tmp_path: Path) -> None:
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteEventRepository(db)
    now = datetime(2025, 12, 25, 12, 0, tzinfo=timezone.utc)

    ev = create_event(repo, CreateEventInput(title="E", day=date(2025, 12, 25)), now=now)

    ev = add_event_note(repo, ev.id, "hello", now=now)
    assert len(ev.notes) == 1
    note_id = ev.notes[0].id
    assert ev.notes[0].text == "hello"

    ev = update_event_note(repo, ev.id, note_id, "updated", now=now)
    assert len(ev.notes) == 1
    assert ev.notes[0].id == note_id
    assert ev.notes[0].text == "updated"

    ev = delete_event_note(repo, ev.id, note_id, now=now)
    assert ev.notes == []


def test_update_missing_note_raises(tmp_path: Path) -> None:
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteEventRepository(db)
    now = datetime(2025, 12, 25, 12, 0, tzinfo=timezone.utc)

    ev = create_event(repo, CreateEventInput(title="E", day=date(2025, 12, 25)), now=now)

    with pytest.raises(ValidationError):
        update_event_note(repo, ev.id, ev.id, "x", now=now)


def test_add_empty_note_rejected(tmp_path: Path) -> None:
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteEventRepository(db)
    now = datetime(2025, 12, 25, 12, 0, tzinfo=timezone.utc)

    ev = create_event(repo, CreateEventInput(title="E", day=date(2025, 12, 25)), now=now)

    with pytest.raises(ValidationError):
        add_event_note(repo, ev.id, "  ", now=now)
