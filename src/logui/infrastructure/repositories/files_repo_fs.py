from __future__ import annotations

from pathlib import Path

from logui.domain.ports.files import FilesRepository


class FsFilesRepository(FilesRepository):
    def __init__(self, base_dir: Path):
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def list_txt_files(self) -> list[str]:
        if not self._base_dir.exists():
            return []

        names: list[str] = []
        for p in self._base_dir.iterdir():
            if not p.is_file():
                continue
            if p.suffix.lower() != ".txt":
                continue
            # Skip hidden files (starting with dot)
            if p.name.startswith("."):
                continue
            names.append(p.name)

        names.sort(key=lambda s: s.lower())
        return names

    def path_for(self, filename: str) -> Path:
        # Hardening: ensure filename doesn't escape base_dir.
        name = Path(filename).name
        return (self._base_dir / name).resolve()

    def create_txt_file(self, filename: str) -> Path:
        path = self.path_for(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        # "x" prevents overwriting existing files.
        with open(path, "x", encoding="utf-8"):
            pass
        return path

    def delete_txt_file(self, filename: str) -> bool:
        path = self.path_for(filename)
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False

    def rename_txt_file(self, old_filename: str, new_filename: str) -> None:
        old_path = self.path_for(old_filename)
        new_path = self.path_for(new_filename)

        if old_path == new_path:
            return

        if not old_path.exists():
            raise FileNotFoundError(str(old_path))
        if new_path.exists():
            raise FileExistsError(str(new_path))

        old_path.rename(new_path)
