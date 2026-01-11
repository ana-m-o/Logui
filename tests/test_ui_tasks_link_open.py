from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult
from textual.widgets import Input, Static


class TasksLinkOpenTestApp(App[None]):
    def __init__(self, repo, **kwargs):
        super().__init__(**kwargs)
        self.repo = repo
        self.notifications: list[str] = []

    def notify(self, message: str, *args, **kwargs) -> None:  # type: ignore[override]
        self.notifications.append(str(message))

    def compose(self) -> ComposeResult:
        from logui.ui.screens.tasks import TasksPane

        yield TasksPane(self.repo)


def test_tasks_open_link_uses_default_browser(tmp_path, monkeypatch) -> None:
    from logui.infrastructure.repositories.tasks_repo_json import JsonTaskRepository
    from logui.ui.screens.tasks import TaskFormScreen, TasksPane

    repo = JsonTaskRepository(tmp_path / "tasks.json")

    opened: list[str] = []

    def _fake_open(url: str, *args, **kwargs) -> bool:
        opened.append(str(url))
        return True

    # Patch the module-level webbrowser used by TasksPane.
    import logui.ui.screens.tasks as tasks_screen

    monkeypatch.setattr(tasks_screen.webbrowser, "open", _fake_open)

    async def _run() -> None:
        app = TasksLinkOpenTestApp(repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            tasks = app.query_one("#tasks", TasksPane)

            tasks.action_new()
            await pilot.pause()
            assert isinstance(app.screen, TaskFormScreen)

            form = app.screen
            form.query_one("#title", Input).value = "T1"
            form.query_one("#link_url", Input).value = "https://example.com"
            form.query_one("#link_text", Input).value = "Example"
            form.action_submit()
            await pilot.pause()

            # 1) Keyboard action still works.
            tasks.action_open_link()
            await pilot.pause()

            # 2) Mouse click on the link widget also opens.
            link_widget = tasks.query_one(".task_link", Static)

            class _Click:
                button = 1
                widget = link_widget

            assert tasks._handle_link_click(_Click()) is True  # noqa: SLF001
            await pilot.pause()

            assert opened == ["https://example.com", "https://example.com"]

    asyncio.run(_run())
