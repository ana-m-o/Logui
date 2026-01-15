"""Test that empty date field in event form always defaults to today."""

from __future__ import annotations

import asyncio
from datetime import date, time, timedelta


def test_edit_event_clearing_date_uses_today(tmp_path, monkeypatch) -> None:
    """When editing an event and clearing the date field, it should use today, not preserve original."""
    from logui.infrastructure.repositories.events_repo_json import JsonEventRepository
    from logui.ui.app import LogUIApp
    from logui.ui.screens.events import EventsPane
    from logui.usecases.events import CreateEventInput, create_event
    from textual.widgets import Input

    monkeypatch.setattr(LogUIApp, "_default_data_dir", lambda self: tmp_path)

    # Create an event with a date in the past (yesterday) but end time in the future to ensure it shows
    repo = JsonEventRepository(tmp_path / "events.json")
    yesterday = date.today() - timedelta(days=1)
    
    event = create_event(
        repo,
        CreateEventInput(
            title="Past event",
            day=yesterday,
            start_time=time(10, 0),
            end_time=time(23, 59),  # Late end time so it shows today (multi-day)
            end_day_offset=1,  # Ends today
        ),
        default_notify_minutes_before=0,
    )

    async def _run() -> None:
        app = LogUIApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Navigate to Events
            await pilot.press("v")
            await pilot.pause()

            content = app.query_one("#content")
            events = content.query_one("#events", EventsPane)

            # Refresh to load the event in the list
            events._refresh()
            await pilot.pause()
            
            # Select the event (should be the only one)
            list_view = events.query_one("#events_list")
            list_view.index = 0
            await pilot.pause()

            # Open edit form
            events.action_edit()
            await pilot.pause()

            # Clear the date field
            date_input = app.screen.query_one("#start_day", Input)
            original_date = date_input.value
            assert original_date == yesterday.isoformat()  # Should be prefilled with yesterday
            
            date_input.value = ""
            await pilot.pause()

            # Submit the form
            app.screen.action_submit()
            await pilot.pause()

            # Verify the event was updated with today's date, not yesterday
            updated_event = repo.get_event(event.id)
            assert updated_event is not None
            assert updated_event.date == date.today(), \
                f"Expected date to be today ({date.today()}), but got {updated_event.date}"

    asyncio.run(_run())


def test_new_event_empty_date_defaults_to_today(tmp_path, monkeypatch) -> None:
    """When creating a new event with empty date field, it should use today."""
    from logui.infrastructure.repositories.events_repo_json import JsonEventRepository
    from logui.ui.app import LogUIApp
    from logui.ui.screens.events import EventsPane
    from textual.widgets import Input

    monkeypatch.setattr(LogUIApp, "_default_data_dir", lambda self: tmp_path)

    async def _run() -> None:
        app = LogUIApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Navigate to Events
            await pilot.press("v")
            await pilot.pause()

            content = app.query_one("#content")
            events = content.query_one("#events", EventsPane)

            # Open new event form
            events.action_new()
            await pilot.pause()

            # Verify date field is empty
            date_input = app.screen.query_one("#start_day", Input)
            assert date_input.value == ""

            # Fill only title and time, leave date empty
            title_input = app.screen.query_one("#title", Input)
            title_input.value = "New event"
            
            time_input = app.screen.query_one("#start_time", Input)
            time_input.value = "14:00"
            
            await pilot.pause()

            # Submit the form
            app.screen.action_submit()
            await pilot.pause()

            # Verify the event was created with today's date
            repo = JsonEventRepository(tmp_path / "events.json")
            all_events = repo.list_events()
            assert len(all_events) == 1
            assert all_events[0].date == date.today(), \
                f"Expected date to be today ({date.today()}), but got {all_events[0].date}"
            assert all_events[0].title == "New event"

    asyncio.run(_run())
