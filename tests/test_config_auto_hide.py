"""Tests for auto-hide completed items configuration."""
from pathlib import Path

from logui.domain.entities.config import AppConfig, UIConfig
from logui.infrastructure.repositories.config_repo_json import JsonConfigRepository
from logui.usecases.config import toggle_auto_hide_completed


def test_ui_config_defaults():
    """UIConfig should default to auto_hide_completed=False."""
    ui = UIConfig()
    assert ui.auto_hide_completed is False


def test_ui_config_from_dict_missing():
    """UIConfig.from_dict should handle missing data gracefully."""
    ui = UIConfig.from_dict(None)
    assert ui.auto_hide_completed is False
    
    ui = UIConfig.from_dict({})
    assert ui.auto_hide_completed is False


def test_ui_config_from_dict_explicit():
    """UIConfig.from_dict should parse explicit values."""
    ui = UIConfig.from_dict({"auto_hide_completed": True})
    assert ui.auto_hide_completed is True
    
    ui = UIConfig.from_dict({"auto_hide_completed": False})
    assert ui.auto_hide_completed is False


def test_ui_config_to_dict():
    """UIConfig.to_dict should serialize correctly."""
    ui = UIConfig(auto_hide_completed=True)
    assert ui.to_dict() == {"auto_hide_completed": True, "show_journal_in_log": False}
    
    ui = UIConfig(auto_hide_completed=False)
    assert ui.to_dict() == {"auto_hide_completed": False, "show_journal_in_log": False}


def test_app_config_includes_ui():
    """AppConfig should include ui field."""
    config = AppConfig.default()
    assert config.ui is not None
    assert isinstance(config.ui, UIConfig)
    assert config.ui.auto_hide_completed is False


def test_app_config_from_dict_with_ui():
    """AppConfig.from_dict should parse ui section."""
    data = {
        "schema_version": 1,
        "ui": {"auto_hide_completed": True},
    }
    config = AppConfig.from_dict(data)
    assert config.ui.auto_hide_completed is True


def test_app_config_to_dict_with_ui():
    """AppConfig.to_dict should include ui section."""
    config = AppConfig(ui=UIConfig(auto_hide_completed=True))
    data = config.to_dict()
    assert "ui" in data
    assert data["ui"]["auto_hide_completed"] is True


def test_toggle_auto_hide_completed(tmp_path: Path):
    """toggle_auto_hide_completed should flip the setting."""
    repo = JsonConfigRepository(tmp_path / "config.json")
    
    # Initial state
    config = repo.load()
    assert config.ui.auto_hide_completed is False
    
    # Toggle to True
    updated = toggle_auto_hide_completed(repo=repo)
    assert updated.ui.auto_hide_completed is True
    
    # Verify it persisted
    reloaded = repo.load()
    assert reloaded.ui.auto_hide_completed is True
    
    # Toggle back to False
    updated2 = toggle_auto_hide_completed(repo=repo)
    assert updated2.ui.auto_hide_completed is False
    
    # Verify persistence again
    reloaded2 = repo.load()
    assert reloaded2.ui.auto_hide_completed is False
