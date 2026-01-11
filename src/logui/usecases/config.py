from __future__ import annotations

import shlex
from datetime import time

from logui.domain.entities.config import (
    AppConfig,
    EditorConfig,
    EncryptionConfig,
    NotificationsConfig,
)
from logui.domain.ports.config import ConfigRepository


def update_editor(*, repo: ConfigRepository, command: str, args_text: str) -> AppConfig:
    current = repo.load()

    cmd = (command or "").strip()
    if not cmd:
        cmd = "nano"

    raw = (args_text or "").strip()
    if raw:
        try:
            args = shlex.split(raw)
        except Exception:  # noqa: BLE001
            # Fallback to a simple split if quoting is malformed.
            args = raw.split()
    else:
        args = []

    updated = AppConfig(
        schema_version=current.schema_version,
        editor=EditorConfig(command=cmd, args=args),
        encryption=current.encryption,
        notifications=current.notifications,
    )
    repo.save(updated)
    return updated


def set_encryption_enabled(*, repo: ConfigRepository, enabled: bool) -> AppConfig:
    current = repo.load()
    updated = AppConfig(
        schema_version=current.schema_version,
        editor=current.editor,
        encryption=EncryptionConfig(enabled=bool(enabled)),
        notifications=current.notifications,
    )
    repo.save(updated)
    return updated


def set_all_day_notify_time(*, repo: ConfigRepository, hhmm: str) -> AppConfig:
    current = repo.load()

    s = (hhmm or "").strip()
    # Validate HH:MM (fallback keeps current value).
    parsed_ok = False
    try:
        hh_s, mm_s = s.split(":", 1)
        hh = int(hh_s)
        mm = int(mm_s)
        time(hh, mm)
        parsed_ok = True
    except Exception:  # noqa: BLE001
        parsed_ok = False

    new_notifications = NotificationsConfig(
        all_day_notify_time=s if parsed_ok else current.notifications.all_day_notify_time,
        default_minutes_before=current.notifications.default_minutes_before,
    )
    updated = AppConfig(
        schema_version=current.schema_version,
        editor=current.editor,
        encryption=current.encryption,
        notifications=new_notifications,
    )
    repo.save(updated)
    return updated


def set_default_notify_minutes_before(*, repo: ConfigRepository, minutes: int) -> AppConfig:
    current = repo.load()
    mins = int(minutes)
    if mins < 0:
        mins = 0

    new_notifications = NotificationsConfig(
        all_day_notify_time=current.notifications.all_day_notify_time,
        default_minutes_before=mins,
    )
    updated = AppConfig(
        schema_version=current.schema_version,
        editor=current.editor,
        encryption=current.encryption,
        notifications=new_notifications,
    )
    repo.save(updated)
    return updated
