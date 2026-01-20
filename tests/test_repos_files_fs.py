from __future__ import annotations

from pathlib import Path

import pytest


def test_fs_files_repo_crud_and_listing(tmp_path: Path) -> None:
    from logui.infrastructure.repositories.files_repo_fs import FsFilesRepository

    repo = FsFilesRepository(tmp_path / "files")

    # Starts empty
    assert repo.list_txt_files() == []

    # Ignores non-txt
    (tmp_path / "files" / "a.md").write_text("x", encoding="utf-8")
    assert repo.list_txt_files() == []

    # Create txt files
    repo.create_txt_file("b.txt")
    repo.create_txt_file("A.txt")

    # Sorted case-insensitively
    assert repo.list_txt_files() == ["A.txt", "b.txt"]

    # Creating existing should fail
    with pytest.raises(FileExistsError):
        repo.create_txt_file("b.txt")

    # Delete
    assert repo.delete_txt_file("b.txt") is True
    assert repo.delete_txt_file("b.txt") is False

    # Rename
    repo.rename_txt_file("A.txt", "c.txt")
    assert repo.list_txt_files() == ["c.txt"]


def test_fs_files_repo_path_for_is_basename(tmp_path: Path) -> None:
    from logui.infrastructure.repositories.files_repo_fs import FsFilesRepository

    repo = FsFilesRepository(tmp_path / "files")

    p = repo.path_for("../escape.txt")
    # path_for hardens to basename, so it ends inside base dir
    assert p.name == "escape.txt"
    assert str(p).startswith(str((tmp_path / "files").resolve()))
