from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Any


@dataclass(frozen=True)
class EditorConfig:
    command: str = "nano"
    args: list[str] | None = None

    def normalized_args(self) -> list[str]:
        return list(self.args or [])

    @staticmethod
    def from_dict(data: dict[str, Any] | None) -> "EditorConfig":
        data = data or {}
        command = str(data.get("command") or "nano")
        raw_args = data.get("args")
        if isinstance(raw_args, list):
            args = [str(a) for a in raw_args]
        elif raw_args is None:
            args = None
        else:
            args = [str(raw_args)]
        return EditorConfig(command=command, args=args)

    def to_dict(self) -> dict[str, Any]:
        doc: dict[str, Any] = {"command": self.command}
        if self.args is not None:
            doc["args"] = list(self.args)
        return doc


@dataclass(frozen=True)
class EncryptionConfig:
    enabled: bool = False

    @staticmethod
    def from_dict(data: dict[str, Any] | None) -> "EncryptionConfig":
        data = data or {}
        return EncryptionConfig(enabled=bool(data.get("enabled", False)))

    def to_dict(self) -> dict[str, Any]:
        return {"enabled": bool(self.enabled)}


@dataclass(frozen=True)
class NotificationsConfig:
    # Stored as HH:MM in config.json for simplicity.
    all_day_notify_time: str = "09:00"
    default_minutes_before: int = 0

    def parsed_all_day_notify_time(self) -> time:
        s = (self.all_day_notify_time or "").strip()
        try:
            hh_s, mm_s = s.split(":", 1)
            hh = int(hh_s)
            mm = int(mm_s)
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                raise ValueError
            return time(hh, mm)
        except Exception:  # noqa: BLE001
            return time(9, 0)

    @staticmethod
    def from_dict(data: dict[str, Any] | None) -> "NotificationsConfig":
        data = data or {}
        raw_time = data.get("all_day_notify_time", "09:00")
        all_day_notify_time = str(raw_time or "09:00")

        raw_default = data.get("default_minutes_before", 0)
        try:
            default_minutes_before = int(raw_default)
        except Exception:  # noqa: BLE001
            default_minutes_before = 0
        if default_minutes_before < 0:
            default_minutes_before = 0

        return NotificationsConfig(
            all_day_notify_time=all_day_notify_time,
            default_minutes_before=default_minutes_before,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "all_day_notify_time": str(self.all_day_notify_time or "09:00"),
            "default_minutes_before": int(self.default_minutes_before),
        }


@dataclass(frozen=True)
class UIConfig:
    auto_hide_completed: bool = False
    theme: str | None = None
    show_journal_in_log: bool = False

    @staticmethod
    def from_dict(data: dict[str, Any] | None) -> "UIConfig":
        data = data or {}
        return UIConfig(
            auto_hide_completed=bool(data.get("auto_hide_completed", False)),
            theme=data.get("theme") if isinstance(data.get("theme"), str) else None,
            show_journal_in_log=bool(data.get("show_journal_in_log", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        result = {
            "auto_hide_completed": bool(self.auto_hide_completed),
            "show_journal_in_log": bool(self.show_journal_in_log),
        }
        if self.theme:
            result["theme"] = str(self.theme)
        return result


@dataclass(frozen=True)
class AppConfig:
    schema_version: int = 1
    editor: EditorConfig = EditorConfig()
    encryption: EncryptionConfig = EncryptionConfig()
    notifications: NotificationsConfig = NotificationsConfig()
    ui: UIConfig = UIConfig()
    # If None/empty, the app will use its default data directory.
    data_directory: str | None = None

    @staticmethod
    def default() -> "AppConfig":
        return AppConfig()

    @staticmethod
    def from_dict(data: dict[str, Any] | None) -> "AppConfig":
        data = data or {}
        schema_version = int(data.get("schema_version", 1) or 1)
        editor_data = data.get("editor") if isinstance(data.get("editor"), dict) else None
        editor = EditorConfig.from_dict(editor_data)
        encryption = EncryptionConfig.from_dict(
            data.get("encryption") if isinstance(data.get("encryption"), dict) else None
        )
        notifications = NotificationsConfig.from_dict(
            data.get("notifications") if isinstance(data.get("notifications"), dict) else None
        )
        ui = UIConfig.from_dict(
            data.get("ui") if isinstance(data.get("ui"), dict) else None
        )
        raw_data_directory = data.get("data_directory")
        data_directory = str(raw_data_directory).strip() if raw_data_directory is not None else ""
        if not data_directory:
            data_directory = None
        return AppConfig(
            schema_version=schema_version,
            editor=editor,
            encryption=encryption,
            notifications=notifications,
            ui=ui,
            data_directory=data_directory,
        )

    def to_dict(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "schema_version": int(self.schema_version),
            "editor": self.editor.to_dict(),
            "encryption": self.encryption.to_dict(),
            "notifications": self.notifications.to_dict(),
            "ui": self.ui.to_dict(),
        }
        if self.data_directory:
            doc["data_directory"] = str(self.data_directory)
        return doc
