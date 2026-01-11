from __future__ import annotations

from datetime import date

from logui.domain.ports.journal import JournalRepository


def get_entry(repo: JournalRepository, day: date) -> str | None:
    return repo.get_entry(day)


def set_entry(repo: JournalRepository, day: date, text: str) -> None:
    repo.set_entry(day, text)


def delete_entry(repo: JournalRepository, day: date) -> bool:
    return repo.delete_entry(day)


def list_entry_days(repo: JournalRepository) -> list[date]:
    return repo.list_entry_days()
