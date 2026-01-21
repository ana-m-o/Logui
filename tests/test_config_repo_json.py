from __future__ import annotations

from logui.domain.entities.config import AppConfig, EncryptionConfig
from logui.infrastructure.repositories.config_repo_json import JsonConfigRepository
from logui.usecases.config import (
    set_all_day_notify_time,
    set_default_notify_minutes_before,
    update_editor,
)


def test_config_repo_load_defaults_and_save_roundtrip(tmp_path) -> None:
    repo = JsonConfigRepository(tmp_path / "config.json")

    cfg = repo.load()
    assert cfg.editor.command
    assert cfg.notifications.all_day_notify_time
    assert cfg.notifications.default_minutes_before == 0

    cfg2 = update_editor(repo=repo, command="nvim", args_text="--clean {file}")
    assert cfg2.editor.command == "nvim"
    assert cfg2.editor.normalized_args() == ["--clean", "{file}"]

    # Updating the editor must not reset other config sections.
    set_all_day_notify_time(repo=repo, hhmm="08:30")
    cfg2b = update_editor(repo=repo, command="vim", args_text="")
    assert cfg2b.notifications.all_day_notify_time == "08:30"

    cfg4 = set_all_day_notify_time(repo=repo, hhmm="08:30")
    assert cfg4.notifications.all_day_notify_time == "08:30"

    cfg5 = set_default_notify_minutes_before(repo=repo, minutes=15)
    assert cfg5.notifications.default_minutes_before == 15

    reloaded = repo.load()
    assert reloaded.editor.command == "vim"
    assert reloaded.notifications.all_day_notify_time == "08:30"
    assert reloaded.notifications.default_minutes_before == 15


def test_config_usecases_preserve_unrelated_fields(tmp_path) -> None:
    repo = JsonConfigRepository(tmp_path / "config.json")
    repo.save(
        AppConfig(
            encryption=EncryptionConfig(enabled=True),
            data_directory=str(tmp_path / "data"),
        )
    )

    cfg1 = update_editor(repo=repo, command="nvim", args_text="")
    assert cfg1.encryption.enabled is True
    assert cfg1.data_directory == str(tmp_path / "data")

    cfg2 = set_all_day_notify_time(repo=repo, hhmm="08:30")
    assert cfg2.encryption.enabled is True
    assert cfg2.data_directory == str(tmp_path / "data")
    assert cfg2.notifications.default_minutes_before == cfg1.notifications.default_minutes_before

    cfg3 = set_default_notify_minutes_before(repo=repo, minutes=15)
    assert cfg3.encryption.enabled is True
    assert cfg3.data_directory == str(tmp_path / "data")
    assert cfg3.notifications.all_day_notify_time == cfg2.notifications.all_day_notify_time
