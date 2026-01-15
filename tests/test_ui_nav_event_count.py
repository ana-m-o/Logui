"""Tests for event count display in navigation sidebar."""

from __future__ import annotations

import asyncio
from datetime import date, time, timedelta

from textual.app import App, ComposeResult

from logui.infrastructure.repositories.events_repo_json import JsonEventRepository
from logui.ui.app import NavItem, Sidebar
from logui.usecases.events import CreateEventInput, create_event


class NavCountTestApp(App[None]):
    def __init__(self, events_repo, **kwargs):
        super().__init__(**kwargs)
        self._events_repo = events_repo

    def compose(self) -> ComposeResult:
        yield Sidebar()

    def update_nav_counts(self) -> None:
        """Mock implementation of update_nav_counts for testing."""
        try:
            from datetime import datetime

            today = datetime.now().date()
            events = self._events_repo.list_events()
            count = 0
            for ev in events:
                # Calculate end day
                end_day = ev.date.fromordinal(ev.date.toordinal() + int(ev.end_day_offset or 0))
                
                # Skip events that ended before today
                if end_day < today:
                    continue
                
                # Skip events that start after today
                if ev.date > today:
                    continue
                
                # For events ending today, check if they've ended (only if they have both start and end time)
                # All-day events (no start_time) are always counted
                if end_day == today and ev.start_time is not None and ev.end_time is not None:
                    end_datetime = datetime.combine(end_day, ev.end_time)
                    if datetime.now() >= end_datetime:
                        continue
                
                count += 1

            nav_item = self.query_one("#events", NavItem)
            if count > 0:
                nav_item.update_label(f"Events [dim]({count})[/dim]")
            else:
                nav_item.update_label("Events")
        except Exception:  # noqa: BLE001
            pass


def test_nav_shows_event_count_with_one_event(tmp_path) -> None:
    """Test that navigation shows (1) when there's one event today."""
    repo = JsonEventRepository(tmp_path / "events.json")
    today = date.today()

    # Create event with end time in the future to ensure it counts
    create_event(
        repo,
        CreateEventInput(
            title="Meeting",
            day=today,
            start_time=time(22, 0),  # Late evening to avoid time-based filtering
            end_time=time(23, 0),
        ),
    )

    async def _run() -> None:
        app = NavCountTestApp(repo)
        async with app.run_test() as pilot:
            await pilot.pause()
            app.update_nav_counts()
            await pilot.pause()

            nav_item = app.query_one("#events", NavItem)
            label_widget = nav_item.query_one("Static")
            # Use render() to get the text content
            from rich.console import Console
            console = Console()
            with console.capture() as capture:
                console.print(label_widget.render())
            text = capture.get()
            assert "Events" in text
            assert "(1)" in text

    asyncio.run(_run())


def test_nav_shows_event_count_with_multiple_events(tmp_path) -> None:
    """Test that navigation shows (3) when there are three events today."""
    repo = JsonEventRepository(tmp_path / "events.json")
    today = date.today()

    # Use late times to avoid time-based filtering
    for i in range(3):
        create_event(
            repo,
            CreateEventInput(
                title=f"Event {i}",
                day=today,
                start_time=time(20 + i, 0),  # 20:00, 21:00, 22:00
                end_time=time(21 + i, 0),  # 21:00, 22:00, 23:00
            ),
        )

    async def _run() -> None:
        app = NavCountTestApp(repo)
        async with app.run_test() as pilot:
            await pilot.pause()
            app.update_nav_counts()
            await pilot.pause()

            nav_item = app.query_one("#events", NavItem)
            label_widget = nav_item.query_one("Static")
            from rich.console import Console
            console = Console()
            with console.capture() as capture:
                console.print(label_widget.render())
            text = capture.get()
            assert "(3)" in text

    asyncio.run(_run())


def test_nav_shows_no_count_when_no_events(tmp_path) -> None:
    """Test that navigation shows just 'Events' when there are no events."""
    repo = JsonEventRepository(tmp_path / "events.json")

    async def _run() -> None:
        app = NavCountTestApp(repo)
        async with app.run_test() as pilot:
            await pilot.pause()
            app.update_nav_counts()
            await pilot.pause()

            nav_item = app.query_one("#events", NavItem)
            label_widget = nav_item.query_one("Static")
            from rich.console import Console
            console = Console()
            with console.capture() as capture:
                console.print(label_widget.render())
            text = capture.get()
            assert "Events" in text
            assert "(" not in text  # No count shown

    asyncio.run(_run())


def test_nav_counts_multiday_event_in_progress(tmp_path) -> None:
    """Test that multi-day events in progress are counted."""
    repo = JsonEventRepository(tmp_path / "events.json")
    today = date.today()
    yesterday = today - timedelta(days=1)

    # Create event that started yesterday and ends today (late to avoid time filtering)
    create_event(
        repo,
        CreateEventInput(
            title="Multi-day event",
            day=yesterday,
            start_time=time(10, 0),
            end_time=time(23, 0),  # Ends late today
            end_day_offset=1,  # Ends today
        ),
    )

    async def _run() -> None:
        app = NavCountTestApp(repo)
        async with app.run_test() as pilot:
            await pilot.pause()
            app.update_nav_counts()
            await pilot.pause()

            nav_item = app.query_one("#events", NavItem)
            label_widget = nav_item.query_one("Static")
            
            # Use Rich Console to capture rendered text
            from rich.console import Console
            console = Console()
            with console.capture() as capture:
                console.print(label_widget.render())
            text = capture.get()
            assert "(1)" in text

    asyncio.run(_run())


def test_nav_does_not_count_past_events(tmp_path) -> None:
    """Test that events from yesterday are not counted."""
    repo = JsonEventRepository(tmp_path / "events.json")
    yesterday = date.today() - timedelta(days=1)

    create_event(
        repo,
        CreateEventInput(
            title="Yesterday event",
            day=yesterday,
            start_time=time(10, 0),
            end_time=time(11, 0),
        ),
    )

    async def _run() -> None:
        app = NavCountTestApp(repo)
        async with app.run_test() as pilot:
            await pilot.pause()
            app.update_nav_counts()
            await pilot.pause()

            nav_item = app.query_one("#events", NavItem)
            label_widget = nav_item.query_one("Static")
            
            # Use Rich Console to capture rendered text
            from rich.console import Console
            console = Console()
            with console.capture() as capture:
                console.print(label_widget.render())
            text = capture.get()
            assert "(" not in text  # No count

    asyncio.run(_run())


def test_nav_does_not_count_future_events(tmp_path) -> None:
    """Test that events from tomorrow are not counted."""
    repo = JsonEventRepository(tmp_path / "events.json")
    tomorrow = date.today() + timedelta(days=1)

    create_event(
        repo,
        CreateEventInput(
            title="Tomorrow event",
            day=tomorrow,
            start_time=time(10, 0),
            end_time=time(11, 0),
        ),
    )

    async def _run() -> None:
        app = NavCountTestApp(repo)
        async with app.run_test() as pilot:
            await pilot.pause()
            app.update_nav_counts()
            await pilot.pause()

            nav_item = app.query_one("#events", NavItem)
            label_widget = nav_item.query_one("Static")
            
            # Use Rich Console to capture rendered text
            from rich.console import Console
            console = Console()
            with console.capture() as capture:
                console.print(label_widget.render())
            text = capture.get()
            assert "(" not in text  # No count

    asyncio.run(_run())


def test_nav_counts_all_day_events(tmp_path) -> None:
    """Test that all-day events today are counted."""
    repo = JsonEventRepository(tmp_path / "events.json")
    today = date.today()

    create_event(
        repo,
        CreateEventInput(
            title="All day event",
            day=today,
            start_time=None,  # All-day
        ),
    )

    async def _run() -> None:
        app = NavCountTestApp(repo)
        async with app.run_test() as pilot:
            await pilot.pause()
            app.update_nav_counts()
            await pilot.pause()

            nav_item = app.query_one("#events", NavItem)
            label_widget = nav_item.query_one("Static")
            
            # Use Rich Console to capture rendered text
            from rich.console import Console
            console = Console()
            with console.capture() as capture:
                console.print(label_widget.render())
            text = capture.get()
            assert "(1)" in text

    asyncio.run(_run())
