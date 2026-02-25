"""Tests for SqliteJournalRepository."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from logui.infrastructure.persistence import SQLiteDatabase
from logui.infrastructure.repositories.journal_repo_sqlite import SqliteJournalRepository


def test_sqlite_journal_repo_empty(tmp_path: Path) -> None:
    """Test repository with no entries."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteJournalRepository(db)

    assert repo.list_entry_days() == []
    assert repo.get_entry(date(2026, 1, 1)) is None


def test_sqlite_journal_repo_set_and_get(tmp_path: Path) -> None:
    """Test setting and getting a journal entry."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteJournalRepository(db)

    day = date(2026, 2, 24)
    text = "Today was a good day!"

    repo.set_entry(day, text)

    # Get entry
    retrieved = repo.get_entry(day)
    assert retrieved == text

    # List should include this day
    days = repo.list_entry_days()
    assert day in days


def test_sqlite_journal_repo_set_overwrites(tmp_path: Path) -> None:
    """Test that setting entry overwrites previous entry."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteJournalRepository(db)

    day = date(2026, 2, 24)

    # Set first entry
    repo.set_entry(day, "First entry")
    assert repo.get_entry(day) == "First entry"

    # Overwrite with second entry
    repo.set_entry(day, "Second entry")
    assert repo.get_entry(day) == "Second entry"

    # Should only have one day in list
    days = repo.list_entry_days()
    assert len([d for d in days if d == day]) == 1


def test_sqlite_journal_repo_delete(tmp_path: Path) -> None:
    """Test deleting a journal entry."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteJournalRepository(db)

    day = date(2026, 2, 24)

    # Set entry
    repo.set_entry(day, "Test entry")
    assert repo.get_entry(day) is not None

    # Delete entry
    deleted = repo.delete_entry(day)
    assert deleted is True

    # Entry should be gone
    assert repo.get_entry(day) is None
    assert day not in repo.list_entry_days()

    # Deleting again should return False
    deleted_again = repo.delete_entry(day)
    assert deleted_again is False


def test_sqlite_journal_repo_list_entry_days_sorted(tmp_path: Path) -> None:
    """Test that list_entry_days returns dates in descending order."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteJournalRepository(db)

    # Add entries in random order
    dates = [
        date(2026, 1, 15),
        date(2026, 3, 1),
        date(2026, 2, 10),
        date(2025, 12, 25),
    ]

    for day in dates:
        repo.set_entry(day, f"Entry for {day}")

    # List should be sorted descending (newest first)
    days = repo.list_entry_days()
    expected = sorted(dates, reverse=True)
    assert days == expected


def test_sqlite_journal_repo_empty_text(tmp_path: Path) -> None:
    """Test setting entry with empty text."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteJournalRepository(db)

    day = date(2026, 2, 24)

    # Set empty entry
    repo.set_entry(day, "")

    # Should save empty string
    text = repo.get_entry(day)
    assert text == ""

    # Empty entries should not appear in list_entry_days
    days = repo.list_entry_days()
    assert day not in days


def test_sqlite_journal_repo_multiline_text(tmp_path: Path) -> None:
    """Test setting entry with multiline text."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteJournalRepository(db)

    day = date(2026, 2, 24)
    text = """Line 1
Line 2
Line 3

Line 5 with blank line above"""

    repo.set_entry(day, text)

    retrieved = repo.get_entry(day)
    assert retrieved == text


def test_sqlite_journal_repo_unicode_text(tmp_path: Path) -> None:
    """Test setting entry with unicode characters."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteJournalRepository(db)

    day = date(2026, 2, 24)
    text = "Hoy fue un día genial! 🎉 ¡Qué bien! 中文测试"

    repo.set_entry(day, text)

    retrieved = repo.get_entry(day)
    assert retrieved == text


def test_sqlite_journal_repo_multiple_entries(tmp_path: Path) -> None:
    """Test repository with multiple entries."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteJournalRepository(db)

    entries = {
        date(2026, 1, 1): "New year!",
        date(2026, 2, 14): "Valentine's day",
        date(2026, 3, 15): "Random day",
    }

    # Add all entries
    for day, text in entries.items():
        repo.set_entry(day, text)

    # Verify all entries
    for day, expected_text in entries.items():
        retrieved = repo.get_entry(day)
        assert retrieved == expected_text

    # Verify list contains all days
    days = repo.list_entry_days()
    for day in entries:
        assert day in days


def test_sqlite_journal_repo_updated_at_tracked(tmp_path: Path) -> None:
    """Test that updated_at timestamp is tracked."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteJournalRepository(db)

    day = date(2026, 2, 24)
    repo.set_entry(day, "Test entry")

    # Check database for updated_at
    conn = db.get_connection()
    cursor = conn.execute(
        """
        SELECT updated_at FROM journal_entries WHERE entry_date = ?
    """,
        (day.isoformat(),),
    )
    row = cursor.fetchone()

    assert row is not None
    assert row[0]  # Should have timestamp

    # Timestamp should be in ISO format with Z
    timestamp = row[0]
    assert timestamp.endswith("Z")
    assert "T" in timestamp


def test_sqlite_journal_repo_roundtrip(tmp_path: Path) -> None:
    """Test complete roundtrip: set, get, delete."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteJournalRepository(db)

    day = date(2025, 12, 25)

    # Initially empty
    assert repo.get_entry(day) is None
    assert repo.list_entry_days() == []

    # Set entry
    repo.set_entry(day, "Hola")
    assert repo.get_entry(day) == "Hola"
    assert repo.list_entry_days() == [day]

    # Delete entry
    assert repo.delete_entry(day) is True
    assert repo.get_entry(day) is None
    assert repo.list_entry_days() == []

    # Delete again (should return False)
    assert repo.delete_entry(day) is False
