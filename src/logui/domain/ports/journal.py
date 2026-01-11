from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date


class JournalRepository(ABC):
    @abstractmethod
    def list_entry_days(self) -> list[date]:
        raise NotImplementedError

    @abstractmethod
    def get_entry(self, day: date) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def set_entry(self, day: date, text: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete_entry(self, day: date) -> bool:
        raise NotImplementedError
