from __future__ import annotations

from abc import ABC, abstractmethod

from logui.domain.entities.config import AppConfig


class ConfigRepository(ABC):
    @abstractmethod
    def load(self) -> AppConfig:
        raise NotImplementedError

    @abstractmethod
    def save(self, config: AppConfig) -> None:
        raise NotImplementedError
