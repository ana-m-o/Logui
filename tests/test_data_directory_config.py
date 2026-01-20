"""Tests for data directory configuration."""

from pathlib import Path

import pytest

from logui.domain.entities.config import AppConfig
from logui.infrastructure.repositories.config_repo_json import JsonConfigRepository
from logui.usecases.data_directory import get_expanded_data_directory, set_data_directory


def test_default_data_directory():
    """Default data directory should be home ~/.logui when no override is set."""
    config = AppConfig.default()
    assert config.data_directory is None
    
    expanded = get_expanded_data_directory(config)
    assert expanded == Path.home() / ".logui"


def test_set_data_directory(tmp_path):
    """Should be able to set custom data directory."""
    config_file = tmp_path / "config.json"
    repo = JsonConfigRepository(config_file)
    
    # Set custom directory
    custom_dir = "~/my_custom_logui_data"
    set_data_directory(repo, custom_dir)
    
    # Verify it was saved
    loaded = repo.load()
    assert loaded.data_directory == custom_dir
    
    # Verify expansion works
    expanded = get_expanded_data_directory(loaded)
    assert expanded == Path.home() / "my_custom_logui_data"


def test_set_data_directory_absolute_path(tmp_path):
    """Should handle absolute paths."""
    config_file = tmp_path / "config.json"
    repo = JsonConfigRepository(config_file)
    
    custom_dir = str(tmp_path / "logui_data")
    set_data_directory(repo, custom_dir)
    
    loaded = repo.load()
    assert loaded.data_directory == custom_dir
    
    expanded = get_expanded_data_directory(loaded)
    assert expanded == Path(custom_dir).resolve()


def test_set_data_directory_empty_defaults(tmp_path):
    """Empty directory should default to ~/.logui."""
    config_file = tmp_path / "config.json"
    repo = JsonConfigRepository(config_file)
    
    set_data_directory(repo, "")
    
    loaded = repo.load()
    assert loaded.data_directory is None

    expanded = get_expanded_data_directory(loaded)
    assert expanded == Path.home() / ".logui"


def test_config_serialization_with_data_directory():
    """Data directory should be serialized and deserialized correctly."""
    config = AppConfig(
        schema_version=1,
        data_directory="~/custom_data"
    )
    
    # Serialize
    data = config.to_dict()
    assert data["data_directory"] == "~/custom_data"
    
    # Deserialize
    restored = AppConfig.from_dict(data)
    assert restored.data_directory == "~/custom_data"


def test_config_backward_compatibility():
    """Old configs without data_directory should default to ~/.logui."""
    # Simulate old config without data_directory field
    old_config_data = {
        "schema_version": 1,
        "editor": {"command": "nano"},
        "encryption": {"enabled": False},
        "notifications": {
            "all_day_notify_time": "09:00",
            "default_minutes_before": 0
        }
    }
    
    config = AppConfig.from_dict(old_config_data)
    assert config.data_directory is None

    expanded = get_expanded_data_directory(config)
    assert expanded == Path.home() / ".logui"


def test_set_data_directory_move_files(tmp_path):
    """If move_files=True, existing data files are copied to the new directory."""
    current_dir = tmp_path / "current"
    new_dir = tmp_path / "new"
    current_dir.mkdir()

    # Seed some fake data
    (current_dir / "events.json").write_text("[]")
    (current_dir / "tasks.json").write_text("[]")
    files_dir = current_dir / "files"
    files_dir.mkdir()
    (files_dir / "hello.txt").write_text("hi")

    # Repo lives in current_dir (like the app)
    repo = JsonConfigRepository(current_dir / "config.json")

    set_data_directory(repo, str(new_dir), move_files=True, current_dir=current_dir)

    assert (new_dir / "events.json").exists()
    assert (new_dir / "tasks.json").exists()
    assert (new_dir / "files" / "hello.txt").read_text() == "hi"
