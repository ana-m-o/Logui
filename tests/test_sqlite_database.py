"""Tests for SQLite database infrastructure."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from logui.infrastructure.persistence import SQLiteDatabase


def test_sqlite_database_init(tmp_path: Path) -> None:
    """Test database initialization."""
    db_path = tmp_path / "test.db"
    db = SQLiteDatabase(db_path)
    
    assert db.db_path == db_path
    assert not db_path.exists()


def test_sqlite_database_get_connection(tmp_path: Path) -> None:
    """Test getting a database connection."""
    db = SQLiteDatabase(tmp_path / "test.db")
    
    conn = db.get_connection()
    assert conn is not None
    assert isinstance(conn, sqlite3.Connection)
    
    # Connection should be reused
    conn2 = db.get_connection()
    assert conn is conn2


def test_sqlite_database_foreign_keys_enabled(tmp_path: Path) -> None:
    """Test that foreign key constraints are enabled."""
    db = SQLiteDatabase(tmp_path / "test.db")
    conn = db.get_connection()
    
    cursor = conn.execute("PRAGMA foreign_keys")
    row = cursor.fetchone()
    assert row[0] == 1  # Foreign keys are ON


def test_sqlite_database_init_schema(tmp_path: Path) -> None:
    """Test schema initialization."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    
    conn = db.get_connection()
    
    # Check that all tables exist
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    
    expected_tables = [
        "config",
        "event_notes",
        "events",
        "journal_entries",
        "schema_version",
        "task_notes",
        "tasks",
    ]
    
    assert sorted(tables) == sorted(expected_tables)


def test_sqlite_database_init_schema_idempotent(tmp_path: Path) -> None:
    """Test that init_schema can be called multiple times safely."""
    db = SQLiteDatabase(tmp_path / "test.db")
    
    db.init_schema()
    db.init_schema()  # Should not raise
    db.init_schema()  # Should not raise
    
    # Verify schema version is correct
    version = db.get_schema_version()
    assert version == SQLiteDatabase.SCHEMA_VERSION


def test_sqlite_database_schema_version(tmp_path: Path) -> None:
    """Test schema version tracking."""
    db = SQLiteDatabase(tmp_path / "test.db")
    
    # Before init, no version
    assert db.get_schema_version() is None
    
    # After init, version should be set
    db.init_schema()
    assert db.get_schema_version() == SQLiteDatabase.SCHEMA_VERSION


def test_sqlite_database_transaction_commit(tmp_path: Path) -> None:
    """Test successful transaction commit."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    
    # Insert data in transaction
    with db.transaction() as conn:
        conn.execute("""
            INSERT INTO journal_entries (date, text, updated_at)
            VALUES ('2026-01-01', 'Test entry', '2026-01-01T10:00:00Z')
        """)
    
    # Verify data was committed
    conn = db.get_connection()
    cursor = conn.execute("SELECT text FROM journal_entries WHERE date = '2026-01-01'")
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == "Test entry"


def test_sqlite_database_transaction_rollback(tmp_path: Path) -> None:
    """Test transaction rollback on exception."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    
    # Insert should be rolled back
    with pytest.raises(ValueError):
        with db.transaction() as conn:
            conn.execute("""
                INSERT INTO journal_entries (date, text, updated_at)
                VALUES ('2026-01-01', 'Test entry', '2026-01-01T10:00:00Z')
            """)
            raise ValueError("Test error")
    
    # Verify data was NOT committed
    conn = db.get_connection()
    cursor = conn.execute("SELECT COUNT(*) FROM journal_entries")
    row = cursor.fetchone()
    assert row[0] == 0


def test_sqlite_database_foreign_key_cascade_delete(tmp_path: Path) -> None:
    """Test that foreign key CASCADE DELETE works."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    
    with db.transaction() as conn:
        # Insert event
        conn.execute("""
            INSERT INTO events (
                id, title, date, end_day_offset, notify,
                created_at, updated_at
            ) VALUES (
                'event-1', 'Test Event', '2026-01-01', 0, 1,
                '2026-01-01T10:00:00Z', '2026-01-01T10:00:00Z'
            )
        """)
        
        # Insert event note
        conn.execute("""
            INSERT INTO event_notes (id, event_id, text, created_at)
            VALUES ('note-1', 'event-1', 'Test note', '2026-01-01T10:00:00Z')
        """)
    
    # Verify note exists
    conn = db.get_connection()
    cursor = conn.execute("SELECT COUNT(*) FROM event_notes WHERE event_id = 'event-1'")
    assert cursor.fetchone()[0] == 1
    
    # Delete event
    with db.transaction() as conn:
        conn.execute("DELETE FROM events WHERE id = 'event-1'")
    
    # Verify note was CASCADE deleted
    cursor = conn.execute("SELECT COUNT(*) FROM event_notes WHERE event_id = 'event-1'")
    assert cursor.fetchone()[0] == 0


def test_sqlite_database_check_constraint_end_day_offset(tmp_path: Path) -> None:
    """Test CHECK constraint on end_day_offset."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    
    # Negative end_day_offset should fail
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction() as conn:
            conn.execute("""
                INSERT INTO events (
                    id, title, date, end_day_offset, notify,
                    created_at, updated_at
                ) VALUES (
                    'event-1', 'Test', '2026-01-01', -1, 1,
                    '2026-01-01T10:00:00Z', '2026-01-01T10:00:00Z'
                )
            """)


def test_sqlite_database_check_constraint_end_time_requires_start_time(tmp_path: Path) -> None:
    """Test CHECK constraint that end_time requires start_time."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    
    # end_time without start_time should fail
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction() as conn:
            conn.execute("""
                INSERT INTO events (
                    id, title, date, start_time, end_time, end_day_offset, notify,
                    created_at, updated_at
                ) VALUES (
                    'event-1', 'Test', '2026-01-01', NULL, '15:00:00', 0, 1,
                    '2026-01-01T10:00:00Z', '2026-01-01T10:00:00Z'
                )
            """)
    
    # start_time without end_time should succeed (all-day event)
    with db.transaction() as conn:
        conn.execute("""
            INSERT INTO events (
                id, title, date, start_time, end_time, end_day_offset, notify,
                created_at, updated_at
            ) VALUES (
                'event-1', 'Test', '2026-01-01', NULL, NULL, 0, 1,
                '2026-01-01T10:00:00Z', '2026-01-01T10:00:00Z'
            )
        """)
    
    # Verify insertion
    conn = db.get_connection()
    cursor = conn.execute("SELECT id FROM events WHERE id = 'event-1'")
    assert cursor.fetchone() is not None


def test_sqlite_database_check_constraint_task_status(tmp_path: Path) -> None:
    """Test CHECK constraint on task status enum."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    
    # Invalid status should fail
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction() as conn:
            conn.execute("""
                INSERT INTO tasks (
                    id, order_num, title, status, priority,
                    created_at, updated_at
                ) VALUES (
                    'task-1', 0, 'Test', 'invalid_status', 0,
                    '2026-01-01T10:00:00Z', '2026-01-01T10:00:00Z'
                )
            """)
    
    # Valid status should succeed
    valid_statuses = ['todo', 'in_progress', 'postponed', 'in_review', 'done']
    for status in valid_statuses:
        with db.transaction() as conn:
            conn.execute("""
                INSERT INTO tasks (
                    id, order_num, title, status, priority,
                    created_at, updated_at
                ) VALUES (
                    ?, 0, 'Test', ?, 0,
                    '2026-01-01T10:00:00Z', '2026-01-01T10:00:00Z'
                )
            """, (f"task-{status}", status))


def test_sqlite_database_config_singleton(tmp_path: Path) -> None:
    """Test that config table enforces singleton constraint."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    
    # Insert config with id=1 should succeed
    with db.transaction() as conn:
        conn.execute("""
            INSERT INTO config (id, schema_version, config_json, updated_at)
            VALUES (1, 1, '{}', '2026-01-01T10:00:00Z')
        """)
    
    # Insert config with id=2 should fail (CHECK constraint)
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction() as conn:
            conn.execute("""
                INSERT INTO config (id, schema_version, config_json, updated_at)
                VALUES (2, 1, '{}', '2026-01-01T10:00:00Z')
            """)


def test_sqlite_database_close(tmp_path: Path) -> None:
    """Test database connection closing."""
    db = SQLiteDatabase(tmp_path / "test.db")
    conn = db.get_connection()
    
    assert conn is not None
    db.close()
    
    # After close, getting connection should create a new one
    new_conn = db.get_connection()
    assert new_conn is not None
    assert new_conn is not conn  # Different connection object


def test_sqlite_database_vacuum(tmp_path: Path) -> None:
    """Test database vacuum operation."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    
    # Vacuum should not raise
    db.vacuum()
    
    # Database should still be functional
    version = db.get_schema_version()
    assert version == SQLiteDatabase.SCHEMA_VERSION


def test_sqlite_database_indexes_created(tmp_path: Path) -> None:
    """Test that all indexes are created."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    
    conn = db.get_connection()
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
    )
    indexes = [row[0] for row in cursor.fetchall()]
    
    expected_indexes = [
        "idx_events_date",
        "idx_event_notes_event_id",
        "idx_tasks_order",
        "idx_tasks_parent",
        "idx_tasks_due_date",
        "idx_task_notes_task_id",
        "idx_journal_date",
    ]
    
    assert sorted(indexes) == sorted(expected_indexes)
