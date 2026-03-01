"""SQLite database management and schema initialization."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_log = logging.getLogger(__name__)


class SQLiteDatabase:
    """Manages SQLite database connection and schema initialization.

    This class handles:
    - Database connection lifecycle
    - Schema creation and versioning
    - Transaction management via context manager
    
    Can be used as a context manager to ensure proper cleanup:
        with SQLiteDatabase(path) as db:
            db.init_schema()
            # ... use db ...
        # db.close() is called automatically
    """

    SCHEMA_VERSION = 3

    def __init__(self, db_path: Path):
        """Initialize database manager.

        Args:
            db_path: Path to the SQLite database file
        """
        self._db_path = db_path
        self._connection: sqlite3.Connection | None = None

    def __enter__(self) -> "SQLiteDatabase":
        """Enter context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager, ensuring database is closed."""
        self.close()

    @property
    def db_path(self) -> Path:
        """Get the database file path."""
        return self._db_path

    def get_connection(self) -> sqlite3.Connection:
        """Get or create a database connection.

        Returns:
            Active SQLite connection
        """
        if self._connection is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,  # Allow multi-threaded access
                timeout=30.0,  # Increase timeout to 30 seconds (default is 5)
            )
            # Enable foreign key constraints
            self._connection.execute("PRAGMA foreign_keys = ON")
            # Use WAL mode for better concurrency (optional, can be removed if issues)
            try:
                self._connection.execute("PRAGMA journal_mode = WAL")
            except sqlite3.Error as e:
                _log.warning("Could not enable WAL mode: %s", e)
        return self._connection

    def close(self) -> None:
        """Close the database connection if open."""
        if self._connection is not None:
            try:
                self._connection.close()
            except sqlite3.Error as e:
                _log.warning("Error closing database connection: %s", e)
            finally:
                self._connection = None

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Context manager for database transactions.

        Usage:
            with db.transaction() as conn:
                conn.execute("INSERT INTO ...")
                conn.execute("UPDATE ...")
            # Auto-commit on success, rollback on exception

        Yields:
            Database connection with active transaction
        """
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def init_schema(self) -> None:
        """Initialize database schema if not exists.

        Creates all tables, indexes, and constraints.
        This is idempotent - safe to call multiple times.
        """
        conn = self.get_connection()

        # Check if schema already exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
        )
        needs_migration = False
        current_version = None
        
        if cursor.fetchone():
            cursor = conn.execute("SELECT version FROM schema_version")
            row = cursor.fetchone()
            if row:
                current_version = row[0]
                if current_version == self.SCHEMA_VERSION:
                    _log.debug("Database schema already initialized (version %d)", row[0])
                    return
                elif current_version < self.SCHEMA_VERSION:
                    needs_migration = True
                    _log.debug("Database schema migration needed: %d -> %d", current_version, self.SCHEMA_VERSION)

        if needs_migration:
            self._migrate_schema(current_version)
            return

        _log.debug("Initializing database schema (version %d)", self.SCHEMA_VERSION)

        with self.transaction() as conn:
            # Schema version table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY
                )
            """)

            conn.execute(
                "INSERT OR REPLACE INTO schema_version (version) VALUES (?)", (self.SCHEMA_VERSION,)
            )

            # Config table (singleton)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS config (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    config_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Events table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    event_date TEXT NOT NULL,
                    start_time TEXT,
                    end_time TEXT,
                    end_day_offset INTEGER NOT NULL DEFAULT 0,
                    notify INTEGER NOT NULL DEFAULT 1,
                    notify_minutes_before INTEGER,
                    repeat_data TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (end_day_offset >= 0),
                    CHECK (end_time IS NULL OR start_time IS NOT NULL)
                )
            """)

            # Event notes table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS event_notes (
                    id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
                )
            """)

            # Tasks table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    parent_id TEXT,
                    task_order REAL NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 0,
                    due_date TEXT,
                    link_url TEXT,
                    link_text TEXT,
                    repeat_data TEXT,
                    completed_at TEXT,
                    archived INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (task_order >= 0),
                    CHECK (status IN ('todo', 'in_progress', 'postponed', 'in_review', 'done')),
                    FOREIGN KEY (parent_id) REFERENCES tasks(id) ON DELETE CASCADE
                )
            """)

            # Task notes table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_notes (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                )
            """)

            # Journal entries table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS journal_entries (
                    entry_date TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Create indexes for performance
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_date ON events(event_date)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_event_notes_event_id ON event_notes(event_id)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_order ON tasks(task_order, created_at)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_id)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_archived ON tasks(archived)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_task_notes_task_id ON task_notes(task_id)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_journal_date ON journal_entries(entry_date DESC)
            """)

        _log.debug("Database schema initialized successfully")

    def _migrate_schema(self, from_version: int | None) -> None:
        """Migrate database schema to current version.

        Args:
            from_version: Current schema version in the database
        """
        if from_version is None:
            _log.error("Cannot migrate from unknown schema version")
            return

        _log.info("Migrating database schema from version %d to %d", from_version, self.SCHEMA_VERSION)

        with self.transaction() as conn:
            # Migration from v2 to v3: Add archived field to tasks
            if from_version == 2 and self.SCHEMA_VERSION >= 3:
                _log.debug("Migrating v2 -> v3: Adding archived field to tasks")
                
                # Add archived column with default value 0 (False)
                conn.execute("""
                    ALTER TABLE tasks ADD COLUMN archived INTEGER NOT NULL DEFAULT 0
                """)
                
                # Create index for archived field
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_tasks_archived ON tasks(archived)
                """)
                
                _log.debug("Migration v2 -> v3 completed")
            
            # Update schema version
            conn.execute(
                "UPDATE schema_version SET version = ?", (self.SCHEMA_VERSION,)
            )

        _log.info("Database schema migration completed successfully")

    def vacuum(self) -> None:
        """Optimize database by rebuilding it.

        This reclaims unused space and defragments the database file.
        Should be called periodically or after large deletions.
        """
        try:
            conn = self.get_connection()
            conn.execute("VACUUM")
            _log.debug("Database vacuumed successfully")
        except sqlite3.Error as e:
            _log.warning("Error vacuuming database: %s", e)

    def get_schema_version(self) -> int | None:
        """Get the current schema version from the database.

        Returns:
            Schema version number, or None if not initialized
        """
        try:
            conn = self.get_connection()
            cursor = conn.execute("SELECT version FROM schema_version")
            row = cursor.fetchone()
            return row[0] if row else None
        except sqlite3.Error:
            return None
