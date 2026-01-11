from __future__ import annotations

import asyncio


def test_ui_navigation_and_open_task_modal(tmp_path, monkeypatch) -> None:
    from logui.ui.app import LogUIApp
    from logui.ui.screens.journal import JournalEditorScreen, JournalPane
    from logui.ui.screens.tasks import TaskFormScreen, TasksPane

    # Prevent touching the real home directory.
    monkeypatch.setattr(LogUIApp, "_default_data_dir", lambda self: tmp_path)

    async def _run() -> None:
        app = LogUIApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            content = app.query_one("#content")
            assert getattr(content, "current", None) == "tasks"

            await pilot.press("v")
            await pilot.pause()
            assert getattr(content, "current", None) == "events"

            await pilot.press("?")
            await pilot.pause()
            assert getattr(content, "current", None) == "config"

            await pilot.press("j")
            await pilot.pause()
            assert getattr(content, "current", None) == "journal"

            await pilot.press("f")
            await pilot.pause()
            assert getattr(content, "current", None) == "files"

            journal = content.query_one("#journal", JournalPane)
            journal.action_new()
            await pilot.pause()
            assert isinstance(app.screen, JournalEditorScreen)

            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, JournalEditorScreen)

            # Open a modal via an action method (avoids focus/binding flakiness).
            await pilot.press("t")
            await pilot.pause()

            content = app.query_one("#content")
            tasks = content.query_one("#tasks", TasksPane)
            tasks.action_new()
            await pilot.pause()

            assert isinstance(app.screen, TaskFormScreen)

            await pilot.press("escape")
            await pilot.pause()

            assert not isinstance(app.screen, TaskFormScreen)

    asyncio.run(_run())
