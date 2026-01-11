from __future__ import annotations

import asyncio
from datetime import date


def test_ongoing_multiday_event_shows_in_events_not_log(tmp_path, monkeypatch) -> None:
    """Regression: eventos multi-día que cruzan 'hoy' deben verse en Events, no en Log."""

    from logui.domain.entities.event import Event
    from logui.infrastructure.repositories.events_repo_json import JsonEventRepository
    from logui.ui.app import LogUIApp
    from logui.ui.screens.events import EventsPane
    from logui.ui.screens.log import LogPane

    fixed_today = date(2026, 1, 7)

    # Prevent touching the real home directory.
    monkeypatch.setattr(LogUIApp, "_default_data_dir", lambda self: tmp_path)

    # Freeze today_local() used by Events/Log filtering.
    import logui.ui.screens.events as events_screen
    import logui.ui.screens.log as log_screen

    monkeypatch.setattr(events_screen, "today_local", lambda: fixed_today)
    monkeypatch.setattr(log_screen, "today_local", lambda: fixed_today)

    # Seed an ongoing multi-day event that started in the past.
    start_day = date(2025, 12, 22)
    end_day = date(2026, 1, 16)
    repo = JsonEventRepository(tmp_path / "events.json")
    ev = Event.create(
        "Cross-year event",
        day=start_day,
        start_time=None,
        end_time=None,
        end_day_offset=(end_day - start_day).days,
    )
    repo.upsert_event(ev)

    async def _run() -> None:
        app = LogUIApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Go to Events and ensure the event is visible.
            await pilot.press("v")
            await pilot.pause()

            content = app.query_one("#content")
            assert getattr(content, "current", None) == "events"

            events_pane = content.query_one("#events", EventsPane)
            assert any(e.title == "Cross-year event" for e in events_pane._events)

            # Go to Log and ensure the event is NOT present.
            await pilot.press("l")
            await pilot.pause()

            content = app.query_one("#content")
            assert getattr(content, "current", None) == "log"

            log_pane = content.query_one("#log", LogPane)
            rendered = "\n".join(log_pane._last_rendered_groups or [])
            assert "Cross-year event" not in rendered

    asyncio.run(_run())
