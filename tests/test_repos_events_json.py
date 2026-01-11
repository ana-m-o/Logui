from __future__ import annotations

from datetime import date, time
from pathlib import Path

from logui.domain.entities.event import Event
from logui.infrastructure.repositories.events_repo_json import JsonEventRepository


def test_events_repo_upsert_list_get_delete(tmp_path: Path) -> None:
    path = tmp_path / "events.json"
    repo = JsonEventRepository(path)

    assert repo.list_events() == []

    ev = Event.create(
        "Meet",
        day=date(2025, 1, 1),
        start_time=time(10, 0),
        end_time=time(11, 0),
        notify=True,
        notify_minutes_before=0,
    )

    repo.upsert_event(ev)

    listed = repo.list_events()
    assert len(listed) == 1
    assert listed[0].id == ev.id

    fetched = repo.get_event(ev.id)
    assert fetched is not None
    assert fetched.title == "Meet"

    deleted = repo.delete_event(ev.id)
    assert deleted is True
    assert repo.get_event(ev.id) is None
    assert repo.list_events() == []


def test_events_repo_delete_missing_returns_false(tmp_path: Path) -> None:
    path = tmp_path / "events.json"
    repo = JsonEventRepository(path)

    ev = Event.create("Meet", day=date(2025, 1, 1))
    assert repo.delete_event(ev.id) is False
