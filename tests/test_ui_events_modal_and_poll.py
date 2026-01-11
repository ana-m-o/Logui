from __future__ import annotations

import asyncio


def test_open_close_new_event_modal(tmp_path, monkeypatch) -> None:
    from logui.ui.app import LogUIApp
    from logui.ui.screens.events import EventFormScreen, EventsPane

    monkeypatch.setattr(LogUIApp, "_default_data_dir", lambda self: tmp_path)

    async def _run() -> None:
        app = LogUIApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Navigate to Events.
            await pilot.press("v")
            await pilot.pause()

            content = app.query_one("#content")
            events = content.query_one("#events", EventsPane)

            events.action_new()
            await pilot.pause()
            assert isinstance(app.screen, EventFormScreen)

            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, EventFormScreen)

    asyncio.run(_run())


def test_poll_event_notifications_no_events(tmp_path, monkeypatch) -> None:
    """Covers the scheduler polling path without relying on time or OS notifications."""

    from logui.ui.app import LogUIApp

    monkeypatch.setattr(LogUIApp, "_default_data_dir", lambda self: tmp_path)

    async def _run() -> None:
        app = LogUIApp()

        # Make repo empty + ensure no notify/sound calls happen.
        monkeypatch.setattr(app._events_repo, "list_events", lambda: [])

        notified: list[str] = []

        def _notify(msg: str) -> None:
            notified.append(msg)

        monkeypatch.setattr(app, "notify", _notify)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._poll_event_notifications()
            await pilot.pause()

        assert notified == []

    asyncio.run(_run())
