"""Tests for compact mode configuration."""

from pathlib import Path

from logui.domain.entities.config import AppConfig, UIConfig
from logui.infrastructure.persistence.sqlite_database import SQLiteDatabase
from logui.infrastructure.repositories.config_repo_sqlite import SqliteConfigRepository
from logui.usecases.config import toggle_compact_mode


def test_ui_config_compact_mode_default():
    """UIConfig should default to compact_mode=False."""
    ui = UIConfig()
    assert ui.compact_mode is False


def test_ui_config_from_dict_compact_mode_missing():
    """UIConfig.from_dict should handle missing compact_mode gracefully."""
    ui = UIConfig.from_dict(None)
    assert ui.compact_mode is False

    ui = UIConfig.from_dict({})
    assert ui.compact_mode is False


def test_ui_config_from_dict_compact_mode_explicit():
    """UIConfig.from_dict should parse explicit compact_mode values."""
    ui = UIConfig.from_dict({"compact_mode": True})
    assert ui.compact_mode is True

    ui = UIConfig.from_dict({"compact_mode": False})
    assert ui.compact_mode is False


def test_ui_config_to_dict_compact_mode():
    """UIConfig.to_dict should serialize compact_mode correctly."""
    ui = UIConfig(compact_mode=True)
    data = ui.to_dict()
    assert data["compact_mode"] is True

    ui = UIConfig(compact_mode=False)
    data = ui.to_dict()
    assert data["compact_mode"] is False


def test_app_config_includes_compact_mode():
    """AppConfig should include compact_mode in ui field."""
    config = AppConfig.default()
    assert config.ui is not None
    assert isinstance(config.ui, UIConfig)
    assert config.ui.compact_mode is False


def test_app_config_from_dict_with_compact_mode():
    """AppConfig.from_dict should parse compact_mode in ui section."""
    data = {
        "schema_version": 1,
        "ui": {"compact_mode": True},
    }
    config = AppConfig.from_dict(data)
    assert config.ui.compact_mode is True


def test_app_config_to_dict_with_compact_mode():
    """AppConfig.to_dict should include compact_mode in ui section."""
    config = AppConfig(ui=UIConfig(compact_mode=True))
    data = config.to_dict()
    assert "ui" in data
    assert data["ui"]["compact_mode"] is True


def test_toggle_compact_mode(tmp_path: Path):
    """toggle_compact_mode should flip the setting."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteConfigRepository(db)

    # Initial state
    config = repo.load()
    assert config.ui.compact_mode is False

    # Toggle to True
    updated = toggle_compact_mode(repo=repo)
    assert updated.ui.compact_mode is True

    # Verify it persisted
    reloaded = repo.load()
    assert reloaded.ui.compact_mode is True

    # Toggle back to False
    updated2 = toggle_compact_mode(repo=repo)
    assert updated2.ui.compact_mode is False

    # Verify persistence again
    reloaded2 = repo.load()
    assert reloaded2.ui.compact_mode is False


def test_compact_mode_roundtrip(tmp_path: Path):
    """compact_mode should survive save/load cycle."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteConfigRepository(db)

    # Save with compact_mode=True
    config = AppConfig(ui=UIConfig(compact_mode=True))
    repo.save(config)

    # Load and verify
    loaded = repo.load()
    assert loaded.ui.compact_mode is True

    # Save with compact_mode=False
    config2 = AppConfig(ui=UIConfig(compact_mode=False))
    repo.save(config2)

    # Load and verify
    loaded2 = repo.load()
    assert loaded2.ui.compact_mode is False


def test_compact_mode_preserves_other_ui_settings(tmp_path: Path):
    """Setting compact_mode should not affect other UI settings."""
    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    repo = SqliteConfigRepository(db)

    # Save config with auto_hide and theme
    config = AppConfig(ui=UIConfig(auto_hide_completed=True, theme="dracula"))
    repo.save(config)

    # Toggle compact_mode
    updated = toggle_compact_mode(repo=repo)

    # Verify other settings are preserved
    assert updated.ui.auto_hide_completed is True
    assert updated.ui.theme == "dracula"
    assert updated.ui.compact_mode is True

    # Verify persistence
    reloaded = repo.load()
    assert reloaded.ui.auto_hide_completed is True
    assert reloaded.ui.theme == "dracula"
    assert reloaded.ui.compact_mode is True
