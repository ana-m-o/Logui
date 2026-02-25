"""Tests for show_journal_in_log configuration."""

from __future__ import annotations

from logui.domain.entities.config import AppConfig, UIConfig
from logui.infrastructure.persistence.sqlite_database import SQLiteDatabase
from logui.infrastructure.repositories.config_repo_sqlite import SqliteConfigRepository
from logui.usecases.config import set_show_journal_in_log


def test_show_journal_in_log_default_false(tmp_path) -> None:
    """By default, show_journal_in_log should be False."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteConfigRepository(db)
    config = repo.load()
    assert config.ui.show_journal_in_log is False


def test_set_show_journal_in_log_enabled(tmp_path) -> None:
    """set_show_journal_in_log should enable the option."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteConfigRepository(db)

    # Initially false
    config = repo.load()
    assert config.ui.show_journal_in_log is False

    # Enable it
    updated = set_show_journal_in_log(repo=repo, enabled=True)
    assert updated.ui.show_journal_in_log is True

    # Verify it persists
    reloaded = repo.load()
    assert reloaded.ui.show_journal_in_log is True


def test_set_show_journal_in_log_disabled(tmp_path) -> None:
    """set_show_journal_in_log should disable the option."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteConfigRepository(db)

    # Enable it first
    config = AppConfig(ui=UIConfig(show_journal_in_log=True))
    repo.save(config)

    # Verify it's enabled
    loaded = repo.load()
    assert loaded.ui.show_journal_in_log is True

    # Disable it
    updated = set_show_journal_in_log(repo=repo, enabled=False)
    assert updated.ui.show_journal_in_log is False

    # Verify it persists
    reloaded = repo.load()
    assert reloaded.ui.show_journal_in_log is False


def test_show_journal_in_log_roundtrip(tmp_path) -> None:
    """show_journal_in_log should survive save/load cycle."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteConfigRepository(db)

    # Save with show_journal_in_log=True
    config = AppConfig(ui=UIConfig(show_journal_in_log=True))
    repo.save(config)

    # Load and verify
    loaded = repo.load()
    assert loaded.ui.show_journal_in_log is True

    # Save with show_journal_in_log=False
    config2 = AppConfig(ui=UIConfig(show_journal_in_log=False))
    repo.save(config2)

    # Load and verify
    loaded2 = repo.load()
    assert loaded2.ui.show_journal_in_log is False


def test_show_journal_in_log_preserves_other_ui_settings(tmp_path) -> None:
    """Setting show_journal_in_log should not affect other UI settings."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteConfigRepository(db)

    # Save config with auto_hide and theme
    config = AppConfig(ui=UIConfig(auto_hide_completed=True, theme="dracula"))
    repo.save(config)

    # Set show_journal_in_log
    updated = set_show_journal_in_log(repo=repo, enabled=True)

    # Verify other settings are preserved
    assert updated.ui.auto_hide_completed is True
    assert updated.ui.theme == "dracula"
    assert updated.ui.show_journal_in_log is True

    # Verify persistence
    reloaded = repo.load()
    assert reloaded.ui.auto_hide_completed is True
    assert reloaded.ui.theme == "dracula"
    assert reloaded.ui.show_journal_in_log is True
