from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Input


class FilesTestApp(App[None]):
    def __init__(self, files_repo, config_repo, **kwargs):
        super().__init__(**kwargs)
        self.files_repo = files_repo
        self.config_repo = config_repo
        self.notifications: list[str] = []

    def notify(self, message: str, *args, **kwargs) -> None:  # type: ignore[override]
        self.notifications.append(str(message))

    def compose(self) -> ComposeResult:
        from logui.ui.screens.files import FilesPane

        yield FilesPane(self.files_repo, self.config_repo)


def test_files_create_delete_open(tmp_path: Path, monkeypatch) -> None:
    from logui.infrastructure.repositories.config_repo_json import JsonConfigRepository
    from logui.infrastructure.repositories.files_repo_fs import FsFilesRepository
    from logui.ui.screens.files import NewFileScreen
    from logui.ui.screens.modals import ConfirmScreen

    files_repo = FsFilesRepository(tmp_path / "files")
    config_repo = JsonConfigRepository(tmp_path / "config.json")

    # Prevent launching a real editor.
    import subprocess

    run_calls: list[list[str]] = []

    def _fake_run(argv, *args, **kwargs):  # noqa: ANN001
        run_calls.append(list(argv))
        return object()

    monkeypatch.setattr(subprocess, "run", _fake_run)

    async def _run() -> None:
        app = FilesTestApp(files_repo, config_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            # Create new file via modal
            await pilot.press("n")
            await pilot.pause()
            assert isinstance(app.screen, NewFileScreen)

            app.screen.query_one("#new_file_name", Input).value = "hello"
            app.screen.action_submit()
            await pilot.pause()

            assert files_repo.list_txt_files() == ["hello.txt"]
            assert any("Archivo creado" in m for m in app.notifications)
            assert run_calls == []  # create does not open

            # Open file (e)
            await pilot.press("e")
            await pilot.pause()
            assert len(run_calls) == 1
            assert run_calls[0][-1].endswith("hello.txt")

            # Rename file (r)
            from logui.ui.screens.files import RenameFileScreen

            await pilot.press("r")
            await pilot.pause()
            assert isinstance(app.screen, RenameFileScreen)

            app.screen.query_one("#rename_file_name", Input).value = "hello2"
            app.screen.action_submit()
            await pilot.pause()

            assert files_repo.list_txt_files() == ["hello2.txt"]
            assert any("Archivo renombrado" in m for m in app.notifications)

            # Delete file
            await pilot.press("x")
            await pilot.pause()
            assert isinstance(app.screen, ConfirmScreen)
            app.screen.action_yes()
            await pilot.pause()

            assert files_repo.list_txt_files() == []
            assert any("Archivo borrado" in m for m in app.notifications)

    asyncio.run(_run())
