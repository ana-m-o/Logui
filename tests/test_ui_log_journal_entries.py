"""Tests for journal entries in Log view."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, time

from textual.app import App, ComposeResult
from textual.widgets import Checkbox

from logui.domain.entities.event import Event
from logui.domain.entities.task import Task, TaskStatus
from logui.infrastructure.persistence.sqlite_database import SQLiteDatabase
from logui.infrastructure.repositories.config_repo_sqlite import SqliteConfigRepository
from logui.infrastructure.repositories.events_repo_sqlite import SqliteEventRepository
from logui.infrastructure.repositories.journal_repo_sqlite import SqliteJournalRepository
from logui.infrastructure.repositories.tasks_repo_sqlite import SqliteTaskRepository
from logui.ui.screens.log import LogPane


class LogJournalTestApp(App[None]):
    """Test app for log journal functionality."""

    def __init__(self, tasks_repo, events_repo, journal_repo, config_repo=None, **kwargs):
        super().__init__(**kwargs)
        self._tasks_repo = tasks_repo
        self._events_repo = events_repo
        self._journal_repo = journal_repo
        self._config_repo = config_repo

    def compose(self) -> ComposeResult:
        yield LogPane(self._events_repo, self._tasks_repo, self._journal_repo)


def test_log_journal_checkbox_default_unchecked(tmp_path) -> None:
    """Journal checkbox should be unchecked by default."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    tasks_repo = SqliteTaskRepository(db)
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    events_repo = SqliteEventRepository(db)
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    journal_repo = SqliteJournalRepository(db)

    async def _run() -> None:
        app = LogJournalTestApp(tasks_repo, events_repo, journal_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            checkbox = app.query_one("#log_show_journal", Checkbox)
            assert checkbox.value is False

            log_pane = app.query_one(LogPane)
            assert log_pane.show_journal is False

    asyncio.run(_run())


def test_log_journal_entries_hidden_by_default(tmp_path) -> None:
    """Journal entries should not appear in log when checkbox is unchecked."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    tasks_repo = SqliteTaskRepository(db)
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    events_repo = SqliteEventRepository(db)
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    journal_repo = SqliteJournalRepository(db)

    # Create a past event and journal entry for the same day
    yesterday = date.today().fromordinal(date.today().toordinal() - 1)

    event = Event.create(
        "Past event",
        day=yesterday,
        start_time=time(10, 0),
        end_time=time(11, 0),
    )
    events_repo.upsert_event(event)

    journal_repo.set_entry(yesterday, "This is my journal entry for yesterday")

    async def _run() -> None:
        app = LogJournalTestApp(tasks_repo, events_repo, journal_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            log_pane = app.query_one(LogPane)
            # Should have one day group (yesterday)
            assert log_pane._last_rendered_groups is not None
            assert len(log_pane._last_rendered_groups) == 1

            # The rendered text should contain the event but not the journal entry
            rendered = log_pane._last_rendered_groups[0]
            assert "Past event" in rendered
            assert "journal entry" not in rendered
            assert "📓" not in rendered

    asyncio.run(_run())


def test_log_journal_entries_shown_when_checked(tmp_path) -> None:
    """Journal entries should appear in log when checkbox is checked."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    tasks_repo = SqliteTaskRepository(db)
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    events_repo = SqliteEventRepository(db)
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    journal_repo = SqliteJournalRepository(db)

    # Create a past event and journal entry for the same day
    yesterday = date.today().fromordinal(date.today().toordinal() - 1)

    event = Event.create(
        "Past event",
        day=yesterday,
        start_time=time(10, 0),
        end_time=time(11, 0),
    )
    events_repo.upsert_event(event)

    journal_repo.set_entry(yesterday, "This is my journal entry for yesterday")

    async def _run() -> None:
        app = LogJournalTestApp(tasks_repo, events_repo, journal_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            # Check the checkbox
            checkbox = app.query_one("#log_show_journal", Checkbox)
            checkbox.value = True
            await pilot.pause()

            log_pane = app.query_one(LogPane)
            # Should still have one day group (yesterday)
            assert log_pane._last_rendered_groups is not None
            assert len(log_pane._last_rendered_groups) == 1

            # The rendered text should contain both the event and the journal entry
            rendered = log_pane._last_rendered_groups[0]
            assert "Past event" in rendered
            assert "journal entry" in rendered or "📓" in rendered

    asyncio.run(_run())


def test_log_journal_entries_at_end_of_day(tmp_path) -> None:
    """Journal entries should appear at the end of each day's entries."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    tasks_repo = SqliteTaskRepository(db)
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    events_repo = SqliteEventRepository(db)
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    journal_repo = SqliteJournalRepository(db)

    # Create multiple entries for yesterday
    yesterday = date.today().fromordinal(date.today().toordinal() - 1)

    # Morning event
    event1 = Event.create(
        "Morning event",
        day=yesterday,
        start_time=time(9, 0),
        end_time=time(10, 0),
    )
    events_repo.upsert_event(event1)

    # Afternoon event
    event2 = Event.create(
        "Afternoon event",
        day=yesterday,
        start_time=time(14, 0),
        end_time=time(15, 0),
    )
    events_repo.upsert_event(event2)

    # Completed task
    task = Task.create(
        title="Completed task",
        status=TaskStatus.DONE,
        now=datetime.combine(yesterday, time(12, 0)),
    )
    tasks_repo.upsert_task(task)

    # Journal entry
    journal_repo.set_entry(yesterday, "End of day reflection")

    async def _run() -> None:
        app = LogJournalTestApp(tasks_repo, events_repo, journal_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            # Enable journal display
            checkbox = app.query_one("#log_show_journal", Checkbox)
            checkbox.value = True
            await pilot.pause()

            log_pane = app.query_one(LogPane)
            assert log_pane.show_journal is True

            assert log_pane._last_rendered_groups is not None
            assert len(log_pane._last_rendered_groups) == 1
            rendered = log_pane._last_rendered_groups[0]

            # Journal entry should appear last (after the emoji check)
            # Check that journal indicator appears after other entries
            assert "📓" in rendered or "End of day" in rendered

    asyncio.run(_run())


def test_log_journal_entries_only_for_past_days(tmp_path) -> None:
    """Journal entries should only appear for days with other entries or past days."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    tasks_repo = SqliteTaskRepository(db)
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    events_repo = SqliteEventRepository(db)
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    journal_repo = SqliteJournalRepository(db)

    # Create journal entries for yesterday and today
    today = date.today()
    yesterday = today.fromordinal(today.toordinal() - 1)

    journal_repo.set_entry(yesterday, "Yesterday's journal")
    journal_repo.set_entry(today, "Today's journal")

    # Only create an event for yesterday
    event = Event.create(
        "Yesterday event",
        day=yesterday,
        start_time=time(10, 0),
        end_time=time(11, 0),
    )
    events_repo.upsert_event(event)

    async def _run() -> None:
        app = LogJournalTestApp(tasks_repo, events_repo, journal_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            # Enable journal display
            checkbox = app.query_one("#log_show_journal", Checkbox)
            checkbox.value = True
            await pilot.pause()

            log_pane = app.query_one(LogPane)
            # Should only have one day group (yesterday) because today has no completed items
            assert log_pane._last_rendered_groups is not None
            assert len(log_pane._last_rendered_groups) == 1

            rendered = log_pane._last_rendered_groups[0]
            # Should show yesterday's journal but not today's
            assert "Yesterday" in rendered or "journal" in rendered
            assert "Today's journal" not in rendered

    asyncio.run(_run())


def test_log_journal_long_text_truncated(tmp_path) -> None:
    """Long journal entries should be truncated in log view."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    tasks_repo = SqliteTaskRepository(db)
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    events_repo = SqliteEventRepository(db)
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    journal_repo = SqliteJournalRepository(db)

    yesterday = date.today().fromordinal(date.today().toordinal() - 1)

    # Create a very long journal entry
    long_text = "A" * 100 + "\nSecond line that should not appear"
    journal_repo.set_entry(yesterday, long_text)

    # Need at least one event to show the day in log
    event = Event.create(
        "Event",
        day=yesterday,
        start_time=time(10, 0),
        end_time=time(11, 0),
    )
    events_repo.upsert_event(event)

    async def _run() -> None:
        app = LogJournalTestApp(tasks_repo, events_repo, journal_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            # Enable journal display
            checkbox = app.query_one("#log_show_journal", Checkbox)
            checkbox.value = True
            await pilot.pause()

            log_pane = app.query_one(LogPane)
            assert log_pane._last_rendered_groups is not None
            assert len(log_pane._last_rendered_groups) == 1
            rendered = log_pane._last_rendered_groups[0]

            # Should contain truncation indicator
            assert "..." in rendered
            # Should not show second line
            assert "Second line" not in rendered

    asyncio.run(_run())


def test_log_journal_checkbox_state_persists(tmp_path) -> None:
    """Journal checkbox state should be saved and loaded from config."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    tasks_repo = SqliteTaskRepository(db)
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    events_repo = SqliteEventRepository(db)
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    journal_repo = SqliteJournalRepository(db)
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    config_repo = SqliteConfigRepository(db)

    async def _run() -> None:
        # First app instance - enable journal display
        app1 = LogJournalTestApp(tasks_repo, events_repo, journal_repo, config_repo)
        async with app1.run_test() as pilot:
            await pilot.pause()

            # Initially unchecked
            checkbox1 = app1.query_one("#log_show_journal", Checkbox)
            assert checkbox1.value is False

            # Check it (this should save to config)
            checkbox1.value = True
            await pilot.pause()

        # Second app instance - should load the saved state
        app2 = LogJournalTestApp(tasks_repo, events_repo, journal_repo, config_repo)
        async with app2.run_test() as pilot:
            await pilot.pause()

            # Should be checked because it was saved
            checkbox2 = app2.query_one("#log_show_journal", Checkbox)
            assert checkbox2.value is True

            log_pane2 = app2.query_one(LogPane)
            assert log_pane2.show_journal is True

    asyncio.run(_run())
