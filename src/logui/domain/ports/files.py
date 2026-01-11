from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class FilesRepository(ABC):
    @abstractmethod
    def list_txt_files(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def path_for(self, filename: str) -> Path:
        raise NotImplementedError

    @abstractmethod
    def create_txt_file(self, filename: str) -> Path:
        raise NotImplementedError

    @abstractmethod
    def delete_txt_file(self, filename: str) -> bool:
        raise NotImplementedError
