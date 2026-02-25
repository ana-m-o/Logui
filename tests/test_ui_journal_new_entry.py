"""Tests for Journal 'new entry' behavior and focus management."""

from __future__ import annotations

import asyncio
from datetime import date

from textual.app import App, ComposeResult
from textual.widgets import ListView, Static

from logui.infrastructure.persistence.sqlite_database import SQLiteDatabase
from logui.infrastructure.repositories.journal_repo_sqlite import SqliteJournalRepository
from logui.ui.screens.journal import JournalEditorScreen, JournalPane


class JournalTestApp(App[None]):
    """Test app for Journal functionality."""

    def __init__(self, journal_repo, **kwargs):
        super().__init__(**kwargs)
        self._journal_repo = journal_repo

    def compose(self) -> ComposeResult:
        yield JournalPane(self._journal_repo)


def test_action_new_always_opens_today_when_no_entry_exists(tmp_path) -> None:
    """When pressing 'n', should always open today's date even if no entry exists."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    journal_repo = SqliteJournalRepository(db)

    # Create entries for previous days but not today
    yesterday = date.today().fromordinal(date.today().toordinal() - 1)
    day_before = date.today().fromordinal(date.today().toordinal() - 2)

    journal_repo.set_entry(yesterday, "Yesterday's entry")
    journal_repo.set_entry(day_before, "Day before entry")

    async def _run() -> None:
        app = JournalTestApp(journal_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            journal_pane = app.query_one(JournalPane)

            # Select yesterday (should be the first item in the list)
            lv = app.query_one("#journal_history_list", ListView)
            lv.index = 0
            await pilot.pause()

            # Verify yesterday is selected
            assert journal_pane.selected_day == yesterday

            # Press 'n' to create a new entry
            journal_pane.action_new()
            await pilot.pause()

            # Should open editor for TODAY, not yesterday
            assert isinstance(app.screen, JournalEditorScreen)
            editor = app.screen
            assert editor._initial_day == date.today()
            assert editor._initial_text == ""  # No entry for today exists

    asyncio.run(_run())


def test_action_new_always_opens_today_when_entry_exists(tmp_path) -> None:
    """When pressing 'n', should open today's entry if it already exists."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    journal_repo = SqliteJournalRepository(db)

    # Create entries for today and previous days
    today = date.today()
    yesterday = date.today().fromordinal(date.today().toordinal() - 1)

    journal_repo.set_entry(today, "Today's existing entry")
    journal_repo.set_entry(yesterday, "Yesterday's entry")

    async def _run() -> None:
        app = JournalTestApp(journal_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            journal_pane = app.query_one(JournalPane)

            # Select yesterday
            lv = app.query_one("#journal_history_list", ListView)
            # Find yesterday's index
            for i, day in enumerate(journal_pane._days_with_entries):
                if day == yesterday:
                    lv.index = i
                    break
            await pilot.pause()

            # Verify yesterday is selected
            assert journal_pane.selected_day == yesterday

            # Press 'n' to edit today's entry
            journal_pane.action_new()
            await pilot.pause()

            # Should open editor for TODAY with existing text
            assert isinstance(app.screen, JournalEditorScreen)
            editor = app.screen
            assert editor._initial_day == today
            assert editor._initial_text == "Today's existing entry"

    asyncio.run(_run())


def test_focus_on_saved_entry_after_creating_new(tmp_path) -> None:
    """After saving a new entry, focus should move to the newly created entry."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    journal_repo = SqliteJournalRepository(db)

    # Create entries for previous days only
    day_25 = date.today().fromordinal(date.today().toordinal() - 5)
    day_26 = date.today().fromordinal(date.today().toordinal() - 4)
    day_29 = date.today().fromordinal(date.today().toordinal() - 1)

    journal_repo.set_entry(day_25, "Entry day 25")
    journal_repo.set_entry(day_29, "Entry day 29")

    async def _run() -> None:
        app = JournalTestApp(journal_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            journal_pane = app.query_one(JournalPane)

            # Select day 29 (first in list, since sorted reverse)
            lv = app.query_one("#journal_history_list", ListView)
            lv.index = 0
            await pilot.pause()
            assert journal_pane.selected_day == day_29

            # Simulate saving a new entry for day 26
            journal_pane._save_entry(day_26, "New entry for day 26")

            # Wait for async events to settle
            # Need extra pauses because the flag is restored AFTER selection
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()

            # After saving, day_26 should be selected
            assert journal_pane.selected_day == day_26, (
                f"Expected {day_26} but got {journal_pane.selected_day}. Days: {journal_pane._days_with_entries}"
            )

            # The ListView should have day_26 focused
            # Days are sorted reverse, so order should be: 29, 26, 25
            expected_idx = None
            for i, day in enumerate(journal_pane._days_with_entries):
                if day == day_26:
                    expected_idx = i
                    break

            assert expected_idx is not None, (
                f"day_26 not found in days list: {journal_pane._days_with_entries}"
            )
            assert lv.index == expected_idx, (
                f"ListView index {lv.index} doesn't match expected {expected_idx}"
            )

    asyncio.run(_run())


def test_no_prev_next_day_bindings(tmp_path) -> None:
    """Bindings for '[', ']', and '.' should not exist in JournalPane."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    journal_repo = SqliteJournalRepository(db)

    async def _run() -> None:
        app = JournalTestApp(journal_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            journal_pane = app.query_one(JournalPane)

            # Get all binding keys
            binding_keys = [b.key for b in journal_pane.BINDINGS]

            # These keys should NOT be in the bindings
            assert "[" not in binding_keys
            assert "]" not in binding_keys
            assert "." not in binding_keys

    asyncio.run(_run())


def test_no_prev_next_today_actions_exist(tmp_path) -> None:
    """Methods action_prev_day, action_next_day, action_today should not exist."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    journal_repo = SqliteJournalRepository(db)

    async def _run() -> None:
        app = JournalTestApp(journal_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            journal_pane = app.query_one(JournalPane)

            # These methods should not exist
            assert not hasattr(journal_pane, "action_prev_day")
            assert not hasattr(journal_pane, "action_next_day")
            assert not hasattr(journal_pane, "action_today")

    asyncio.run(_run())


def test_help_text_no_day_navigation_hints(tmp_path) -> None:
    """Help text should not mention '/ day' or '. today'."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    journal_repo = SqliteJournalRepository(db)

    async def _run() -> None:
        app = JournalTestApp(journal_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            journal_pane = app.query_one(JournalPane)

            # Get the help static widget and extract its actual text content
            help_widgets = journal_pane.query(".page_help")
            if help_widgets:
                help_static = help_widgets.first()
                # Get the actual rendered content
                help_str = str(help_static.render())

                # Should not contain these strings
                assert "/ day" not in help_str
                assert ". today" not in help_str

                # Should contain the expected bindings
                assert "n new" in help_str or "new" in help_str
                assert "edit" in help_str
                assert "delete" in help_str

    asyncio.run(_run())


def test_reactiveselected_day_updates_detail(tmp_path) -> None:
    """The reactive selected_day attribute should automatically update the detail view."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    journal_repo = SqliteJournalRepository(db)

    # Create multiple entries
    today = date.today()
    yesterday = date.today().fromordinal(date.today().toordinal() - 1)
    day_before = date.today().fromordinal(date.today().toordinal() - 2)

    journal_repo.set_entry(today, "Today's entry")
    journal_repo.set_entry(yesterday, "Yesterday's entry")
    journal_repo.set_entry(day_before, "Day before entry")

    async def _run() -> None:
        app = JournalTestApp(journal_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            journal_pane = app.query_one(JournalPane)

            # The selected_day should be set by ListView when mounted
            assert journal_pane.selected_day is not None

            # Directly set selected_day via ListView (simulating user navigation)
            lv = app.query_one("#journal_history_list", ListView)
            for i, day in enumerate(journal_pane._days_with_entries):
                if day == day_before:
                    lv.index = i
                    break

            await pilot.pause()

            # The selected_day should be updated automatically by the Highlighted event
            assert journal_pane.selected_day == day_before

            # And the detail view should show the correct content
            detail_text = journal_pane.query_one("#journal_detail_text", Static)
            # Use render() to get the widget's content, not renderable
            rendered_content = str(detail_text.render())
            assert "Day before entry" in rendered_content

    asyncio.run(_run())
