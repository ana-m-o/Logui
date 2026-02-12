"""Tests for auto-hide completed items behavior."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta

from textual.app import App, ComposeResult

from logui.domain.entities.config import AppConfig, UIConfig
from logui.domain.entities.event import Event
from logui.domain.entities.task import Task, TaskStatus
from logui.infrastructure.repositories.config_repo_json import JsonConfigRepository
from logui.infrastructure.repositories.events_repo_json import JsonEventRepository
from logui.infrastructure.repositories.journal_repo_json import JsonJournalRepository
from logui.infrastructure.repositories.tasks_repo_json import JsonTaskRepository
from logui.ui.screens.events import EventsPane
from logui.ui.screens.log import LogPane
from logui.ui.screens.tasks import TasksPane


class AutoHideTestApp(App[None]):
    """Test app with config repo."""

    def __init__(self, tasks_repo, events_repo, config_repo, **kwargs):
        super().__init__(**kwargs)
        self._tasks_repo = tasks_repo
        self._events_repo = events_repo
        self._config_repo = config_repo
        # Create a dummy journal_repo for LogPane (not used in these tests)
        import tempfile
        from pathlib import Path
        self._journal_repo = JsonJournalRepository(Path(tempfile.gettempdir()) / "dummy_journal.json")

    def compose(self) -> ComposeResult:
        yield TasksPane(self._tasks_repo)
        yield EventsPane(self._events_repo)
        yield LogPane(self._events_repo, self._tasks_repo, self._journal_repo)


def test_tasks_auto_hide_filters_completed_today(tmp_path) -> None:
    """When auto_hide is enabled, completed tasks from today should not appear."""
    tasks_repo = JsonTaskRepository(tmp_path / "tasks.json")
    events_repo = JsonEventRepository(tmp_path / "events.json")
    config_repo = JsonConfigRepository(tmp_path / "config.json")

    # Create two tasks: one DONE, one TODO
    task_done = Task.create(
        title="Done task",
        status=TaskStatus.DONE,
        now=datetime.now(),
    )
    task_todo = Task.create(
        title="Todo task",
        status=TaskStatus.TODO,
    )
    tasks_repo.upsert_task(task_done)
    tasks_repo.upsert_task(task_todo)

    async def _run() -> None:
        # Test with auto_hide enabled
        config = AppConfig(ui=UIConfig(auto_hide_completed=True))
        config_repo.save(config)

        app = AutoHideTestApp(tasks_repo, events_repo, config_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            tasks_pane = app.query_one(TasksPane)
            # Should only show the TODO task (DONE task is hidden)
            assert len(tasks_pane._rows) == 1
            assert tasks_pane._rows[0].task.title == "Todo task"

    asyncio.run(_run())


def test_tasks_auto_hide_disabled_shows_completed_today(tmp_path) -> None:
    """When auto_hide is disabled, completed tasks from today should appear."""
    tasks_repo = JsonTaskRepository(tmp_path / "tasks.json")
    events_repo = JsonEventRepository(tmp_path / "events.json")
    config_repo = JsonConfigRepository(tmp_path / "config.json")

    # Create two tasks: one DONE, one TODO
    task_done = Task.create(
        title="Done task",
        status=TaskStatus.DONE,
        now=datetime.now(),
    )
    task_todo = Task.create(
        title="Todo task",
        status=TaskStatus.TODO,
    )
    tasks_repo.upsert_task(task_done)
    tasks_repo.upsert_task(task_todo)

    async def _run() -> None:
        # Test with auto_hide disabled (default)
        config = AppConfig(ui=UIConfig(auto_hide_completed=False))
        config_repo.save(config)

        app = AutoHideTestApp(tasks_repo, events_repo, config_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            tasks_pane = app.query_one(TasksPane)
            # Should show both tasks
            assert len(tasks_pane._rows) == 2

    asyncio.run(_run())


def test_tasks_old_completed_always_hidden(tmp_path) -> None:
    """Completed tasks from previous days should always be hidden."""
    tasks_repo = JsonTaskRepository(tmp_path / "tasks.json")
    events_repo = JsonEventRepository(tmp_path / "events.json")
    config_repo = JsonConfigRepository(tmp_path / "config.json")

    # Create a task completed yesterday
    yesterday = datetime.now() - timedelta(days=1)
    task_old = Task.create(
        title="Old done task",
        status=TaskStatus.DONE,
        now=yesterday,
    )
    task_todo = Task.create(
        title="Todo task",
        status=TaskStatus.TODO,
    )
    tasks_repo.upsert_task(task_old)
    tasks_repo.upsert_task(task_todo)

    async def _run() -> None:
        # Test with auto_hide disabled
        config = AppConfig(ui=UIConfig(auto_hide_completed=False))
        config_repo.save(config)

        app = AutoHideTestApp(tasks_repo, events_repo, config_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            tasks_pane = app.query_one(TasksPane)
            # Should only show the TODO task (old DONE task is always hidden)
            assert len(tasks_pane._rows) == 1
            assert tasks_pane._rows[0].task.title == "Todo task"

    asyncio.run(_run())


def test_events_auto_hide_filters_ended_today(tmp_path) -> None:
    """When auto_hide is enabled, ended events from today should not appear."""
    tasks_repo = JsonTaskRepository(tmp_path / "tasks.json")
    events_repo = JsonEventRepository(tmp_path / "events.json")
    config_repo = JsonConfigRepository(tmp_path / "config.json")

    today = date.today()
    now = datetime.now()

    # Create an event that ended 1 hour ago
    ended_event = Event.create(
        title="Ended event",
        day=today,
        start_time=time((now.hour - 2) % 24, 0),
        end_time=time((now.hour - 1) % 24, 0),
    )
    # Create an ongoing event
    ongoing_event = Event.create(
        title="Ongoing event",
        day=today,
        start_time=time((now.hour - 1) % 24, 0),
        end_time=time((now.hour + 1) % 24, 0),
    )
    events_repo.upsert_event(ended_event)
    events_repo.upsert_event(ongoing_event)

    async def _run() -> None:
        # Test with auto_hide enabled
        config = AppConfig(ui=UIConfig(auto_hide_completed=True))
        config_repo.save(config)

        app = AutoHideTestApp(tasks_repo, events_repo, config_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            events_pane = app.query_one(EventsPane)
            # Should only show the ongoing event (ended event is hidden)
            assert len(events_pane._events) == 1
            assert events_pane._events[0].title == "Ongoing event"

    asyncio.run(_run())


def test_events_auto_hide_disabled_shows_ended_today(tmp_path) -> None:
    """When auto_hide is disabled, ended events from today should appear."""
    tasks_repo = JsonTaskRepository(tmp_path / "tasks.json")
    events_repo = JsonEventRepository(tmp_path / "events.json")
    config_repo = JsonConfigRepository(tmp_path / "config.json")

    today = date.today()
    now = datetime.now()

    # Create an event that ended 1 hour ago
    ended_event = Event.create(
        title="Ended event",
        day=today,
        start_time=time((now.hour - 2) % 24, 0),
        end_time=time((now.hour - 1) % 24, 0),
    )
    events_repo.upsert_event(ended_event)

    async def _run() -> None:
        # Test with auto_hide disabled (default)
        config = AppConfig(ui=UIConfig(auto_hide_completed=False))
        config_repo.save(config)

        app = AutoHideTestApp(tasks_repo, events_repo, config_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            events_pane = app.query_one(EventsPane)
            # Should show the ended event
            assert len(events_pane._events) == 1
            assert events_pane._events[0].title == "Ended event"

    asyncio.run(_run())


def test_log_includes_today_when_auto_hide_enabled(tmp_path) -> None:
    """When auto_hide is enabled, log should include completed items from today."""
    tasks_repo = JsonTaskRepository(tmp_path / "tasks.json")
    events_repo = JsonEventRepository(tmp_path / "events.json")
    config_repo = JsonConfigRepository(tmp_path / "config.json")

    # Create a task completed today
    task_done = Task.create(
        title="Done task today",
        status=TaskStatus.DONE,
        now=datetime.now(),
    )
    tasks_repo.upsert_task(task_done)

    async def _run() -> None:
        # Test with auto_hide enabled
        config = AppConfig(ui=UIConfig(auto_hide_completed=True))
        config_repo.save(config)

        app = AutoHideTestApp(tasks_repo, events_repo, config_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            log_pane = app.query_one(LogPane)
            # Log should include today's items when auto_hide is enabled
            # Check that _last_rendered_groups is not empty
            assert log_pane._last_rendered_groups is not None
            assert len(log_pane._last_rendered_groups) > 0

    asyncio.run(_run())


def test_log_excludes_today_when_auto_hide_disabled(tmp_path) -> None:
    """When auto_hide is disabled, log should NOT include items from today."""
    tasks_repo = JsonTaskRepository(tmp_path / "tasks.json")
    events_repo = JsonEventRepository(tmp_path / "events.json")
    config_repo = JsonConfigRepository(tmp_path / "config.json")

    # Create a task completed today
    task_done = Task.create(
        title="Done task today",
        status=TaskStatus.DONE,
        now=datetime.now(),
    )
    tasks_repo.upsert_task(task_done)

    async def _run() -> None:
        # Test with auto_hide disabled (default)
        config = AppConfig(ui=UIConfig(auto_hide_completed=False))
        config_repo.save(config)

        app = AutoHideTestApp(tasks_repo, events_repo, config_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            log_pane = app.query_one(LogPane)
            # Log should be empty (or show "No past events" message) when auto_hide is disabled
            # because today's items are not included
            assert log_pane._last_rendered_groups is not None
            # Should either be empty or contain the "No past events" message
            if len(log_pane._last_rendered_groups) > 0:
                assert "No past events" in log_pane._last_rendered_groups[0]

    asyncio.run(_run())


def test_all_day_events_never_filtered_by_auto_hide(tmp_path) -> None:
    """All-day events should never be filtered by auto_hide (they don't end until midnight)."""
    tasks_repo = JsonTaskRepository(tmp_path / "tasks.json")
    events_repo = JsonEventRepository(tmp_path / "events.json")
    config_repo = JsonConfigRepository(tmp_path / "config.json")

    today = date.today()

    # Create an all-day event
    all_day_event = Event.create(
        title="All day event",
        day=today,
        start_time=None,  # All-day event
        end_time=None,
    )
    events_repo.upsert_event(all_day_event)

    async def _run() -> None:
        # Test with auto_hide enabled
        config = AppConfig(ui=UIConfig(auto_hide_completed=True))
        config_repo.save(config)

        app = AutoHideTestApp(tasks_repo, events_repo, config_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            events_pane = app.query_one(EventsPane)
            # All-day event should always be visible
            assert len(events_pane._events) == 1
            assert events_pane._events[0].title == "All day event"

    asyncio.run(_run())


def test_task_not_archived_if_reopened_before_auto_hide_timeout(tmp_path) -> None:
    """If a task is marked DONE then returned to TODO before the auto-hide timeout,
    it must not be archived."""
    tasks_repo = JsonTaskRepository(tmp_path / "tasks.json")
    events_repo = JsonEventRepository(tmp_path / "events.json")
    config_repo = JsonConfigRepository(tmp_path / "config.json")

    # Create a task that is one step before DONE so a single cycle reaches DONE
    task = Task.create(title="Flaky task", status=TaskStatus.IN_REVIEW)
    tasks_repo.upsert_task(task)

    async def _run() -> None:
        # Enable auto-hide
        config = AppConfig(ui=UIConfig(auto_hide_completed=True))
        config_repo.save(config)

        app = AutoHideTestApp(tasks_repo, events_repo, config_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            tasks_pane = app.query_one(TasksPane)
            lv = tasks_pane.query_one("#tasks_list")

            # Select the only task
            lv.index = 0

            # Mark as DONE (schedules hide)
            tasks_pane.action_cycle_status()

            # Immediately mark back to next status (DONE -> TODO)
            tasks_pane.action_cycle_status()

            # Force the recorded timestamp to be older than the threshold to simulate time passing
            import time
            for k in list(tasks_pane._tasks_to_hide.keys()):
                tasks_pane._tasks_to_hide[k] = time.time() - 10.0

            # Run the auto-hide check
            tasks_pane._check_auto_hide_tasks()

            # The task must still be present and not archived
            assert len(tasks_pane._rows) == 1
            assert tasks_pane._rows[0].task.status == TaskStatus.TODO

    asyncio.run(_run())


def test_archived_tasks_appear_in_log(tmp_path) -> None:
    """Tasks that are auto-hidden from the tasks list should still appear in the Log."""
    tasks_repo = JsonTaskRepository(tmp_path / "tasks.json")
    events_repo = JsonEventRepository(tmp_path / "events.json")
    config_repo = JsonConfigRepository(tmp_path / "config.json")

    # Create a task one step before DONE so a single cycle reaches DONE
    task = Task.create(title="To be archived", status=TaskStatus.IN_REVIEW)
    tasks_repo.upsert_task(task)

    async def _run() -> None:
        # Enable auto-hide
        config = AppConfig(ui=UIConfig(auto_hide_completed=True))
        config_repo.save(config)

        app = AutoHideTestApp(tasks_repo, events_repo, config_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            tasks_pane = app.query_one(TasksPane)
            lv = tasks_pane.query_one("#tasks_list")

            # Select the task and mark as DONE
            lv.index = 0
            tasks_pane.action_cycle_status()

            # Ensure repository recorded the task as DONE
            repo_task = tasks_repo.get_task(task.id)
            assert repo_task is not None
            assert repo_task.status == TaskStatus.DONE

            # Force the recorded timestamp to be older than the threshold to simulate time passing
            import time
            for k in list(tasks_pane._tasks_to_hide.keys()):
                tasks_pane._tasks_to_hide[k] = time.time() - 10.0

            # Run the auto-hide check (removes from tasks list UI)
            tasks_pane._check_auto_hide_tasks()

            # Repository should still have the completed task
            repo_task_after = tasks_repo.get_task(task.id)
            assert repo_task_after is not None
            assert repo_task_after.status == TaskStatus.DONE

            # Now load the log and ensure the completed task is present
            log_pane = app.query_one(LogsPane) if False else app.query_one("#log")
            # Prefer the actual LogPane instance
            from logui.ui.screens.log import LogPane
            log_pane = app.query_one(LogPane)
            log_pane._load_log()

            # The log should include the completed task title in its rendered groups
            found = False
            if log_pane._last_rendered_groups:
                for g in log_pane._last_rendered_groups:
                    if "To be archived" in g:
                        found = True
                        break
            assert found, "Archived task not found in Log"

    asyncio.run(_run())
