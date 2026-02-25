"""Tests for SqliteConfigRepository."""

from __future__ import annotations

from pathlib import Path

from logui.domain.entities.config import AppConfig, EditorConfig, UIConfig
from logui.infrastructure.persistence import SQLiteDatabase
from logui.infrastructure.repositories.config_repo_sqlite import SqliteConfigRepository


def test_sqlite_config_repo_load_default(tmp_path: Path) -> None:
    """Test loading config when none exists returns default."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteConfigRepository(db)

    config = repo.load()
    assert config is not None
    assert config == AppConfig.default()


def test_sqlite_config_repo_save_and_load(tmp_path: Path) -> None:
    """Test saving and loading config."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteConfigRepository(db)

    # Create custom config
    custom_config = AppConfig(
        schema_version=1,
        editor=EditorConfig(command="vim", args=["-n"]),
        ui=UIConfig(theme="dark", auto_hide_completed=True),
        data_directory="/custom/path",
    )

    # Save
    repo.save(custom_config)

    # Load and verify
    loaded = repo.load()
    assert loaded.schema_version == 1
    assert loaded.editor.command == "vim"
    assert loaded.editor.args == ["-n"]
    assert loaded.ui.theme == "dark"
    assert loaded.ui.auto_hide_completed is True
    assert loaded.data_directory == "/custom/path"


def test_sqlite_config_repo_save_overwrites(tmp_path: Path) -> None:
    """Test that saving config overwrites previous config."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteConfigRepository(db)

    # Save first config
    config1 = AppConfig(
        editor=EditorConfig(command="nano"),
        ui=UIConfig(theme="light"),
    )
    repo.save(config1)

    # Save second config
    config2 = AppConfig(
        editor=EditorConfig(command="vim"),
        ui=UIConfig(theme="dark"),
    )
    repo.save(config2)

    # Load and verify it's the second config
    loaded = repo.load()
    assert loaded.editor.command == "vim"
    assert loaded.ui.theme == "dark"

    # Verify only one row exists in config table
    conn = db.get_connection()
    cursor = conn.execute("SELECT COUNT(*) FROM config")
    assert cursor.fetchone()[0] == 1


def test_sqlite_config_repo_complex_config(tmp_path: Path) -> None:
    """Test saving and loading complex nested config."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteConfigRepository(db)

    # Create complex config with all fields
    config = AppConfig(
        schema_version=1,
        editor=EditorConfig(
            command="code",
            args=["--wait", "--new-window"],
        ),
        ui=UIConfig(
            theme="monokai",
            auto_hide_completed=True,
            show_journal_in_log=True,
        ),
        data_directory="/home/user/.config/logui/data",
    )

    repo.save(config)
    loaded = repo.load()

    # Verify all nested fields
    assert loaded.editor.command == "code"
    assert loaded.editor.args == ["--wait", "--new-window"]
    assert loaded.ui.theme == "monokai"
    assert loaded.ui.auto_hide_completed is True
    assert loaded.ui.show_journal_in_log is True
    assert loaded.data_directory == "/home/user/.config/logui/data"


def test_sqlite_config_repo_updated_at_tracked(tmp_path: Path) -> None:
    """Test that updated_at timestamp is tracked."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteConfigRepository(db)

    config = AppConfig.default()
    repo.save(config)

    # Check that updated_at was set
    conn = db.get_connection()
    cursor = conn.execute("SELECT updated_at FROM config WHERE id = 1")
    row = cursor.fetchone()
    assert row is not None
    assert row[0]  # Should have a timestamp

    # Timestamp should be in ISO format with Z
    timestamp = row[0]
    assert timestamp.endswith("Z")
    assert "T" in timestamp


def test_sqlite_config_repo_none_data_directory(tmp_path: Path) -> None:
    """Test config with None data_directory."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteConfigRepository(db)

    config = AppConfig(data_directory=None)
    repo.save(config)

    loaded = repo.load()
    assert loaded.data_directory is None


def test_sqlite_config_repo_empty_string_data_directory(tmp_path: Path) -> None:
    """Test config with empty string data_directory is treated as None."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()
    repo = SqliteConfigRepository(db)

    # Save with empty string (should normalize to None via AppConfig)
    config_dict = AppConfig.default().to_dict()
    config_dict["data_directory"] = ""
    config = AppConfig.from_dict(config_dict)
    repo.save(config)

    loaded = repo.load()
    # Empty string should be normalized to None by AppConfig.from_dict
    assert loaded.data_directory is None


def test_sqlite_config_repo_corrupted_json_returns_default(tmp_path: Path) -> None:
    """Test that corrupted JSON in database returns default config."""
    db = SQLiteDatabase(tmp_path / "test.db")
    db.init_schema()

    # Manually insert corrupted JSON
    with db.transaction() as conn:
        conn.execute("""
            INSERT INTO config (id, config_json, updated_at)
            VALUES (1, 'invalid json{', '2026-01-01T10:00:00Z')
        """)

    repo = SqliteConfigRepository(db)
    config = repo.load()

    # Should return default config on error
    assert config == AppConfig.default()
