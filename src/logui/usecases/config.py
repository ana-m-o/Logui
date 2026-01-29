from __future__ import annotations

import shlex
from dataclasses import replace
from datetime import time

from logui.domain.entities.config import (
    AppConfig,
    EditorConfig,
    NotificationsConfig,
    UIConfig,
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

    updated = replace(current, editor=EditorConfig(command=cmd, args=args))
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

    new_notifications = replace(
        current.notifications,
        all_day_notify_time=s if parsed_ok else current.notifications.all_day_notify_time,
    )
    updated = replace(current, notifications=new_notifications)
    repo.save(updated)
    return updated


def set_default_notify_minutes_before(*, repo: ConfigRepository, minutes: int) -> AppConfig:
    current = repo.load()
    mins = int(minutes)
    if mins < 0:
        mins = 0

    new_notifications = replace(current.notifications, default_minutes_before=mins)
    updated = replace(current, notifications=new_notifications)
    repo.save(updated)
    return updated


def toggle_auto_hide_completed(*, repo: ConfigRepository) -> AppConfig:
    """Toggle the auto-hide completed items setting."""
    current = repo.load()
    new_ui = replace(current.ui, auto_hide_completed=not current.ui.auto_hide_completed)
    updated = replace(current, ui=new_ui)
    repo.save(updated)
    return updated


def set_theme(*, repo: ConfigRepository, theme_name: str) -> AppConfig:
    """Set the theme in configuration."""
    current = repo.load()
    new_ui = replace(current.ui, theme=theme_name)
    updated = replace(current, ui=new_ui)
    repo.save(updated)
    return updated
