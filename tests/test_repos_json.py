from __future__ import annotations

from datetime import date

from logui.domain.entities import Task
from logui.infrastructure.repositories import JsonJournalRepository, JsonTaskRepository


def test_json_task_repo_roundtrip(tmp_path) -> None:
    repo = JsonTaskRepository(tmp_path / "tasks.json")

    assert repo.list_tasks() == []

    task = Task.create("Tarea 1")
    repo.upsert_task(task)

    loaded = repo.get_task(task.id)
    assert loaded is not None
    assert loaded.title == "Tarea 1"

    assert len(repo.list_tasks()) == 1

    assert repo.delete_task(task.id) is True
    assert repo.get_task(task.id) is None
    assert repo.list_tasks() == []


def test_json_journal_repo_roundtrip(tmp_path) -> None:
    repo = JsonJournalRepository(tmp_path / "journal.json")

    day = date(2025, 12, 25)
    assert repo.get_entry(day) is None

    assert repo.list_entry_days() == []

    repo.set_entry(day, "Hola")
    assert repo.get_entry(day) == "Hola"

    assert repo.list_entry_days() == [day]

    assert repo.delete_entry(day) is True
    assert repo.get_entry(day) is None

    assert repo.list_entry_days() == []

    assert repo.delete_entry(day) is False


def test_json_journal_repo_list_days_sorted_desc(tmp_path) -> None:
    repo = JsonJournalRepository(tmp_path / "journal.json")

    d1 = date(2025, 12, 24)
    d2 = date(2025, 12, 25)
    d3 = date(2025, 12, 26)

    repo.set_entry(d1, "a")
    repo.set_entry(d3, "c")
    repo.set_entry(d2, "b")

    assert repo.list_entry_days() == [d3, d2, d1]
