from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

_log = logging.getLogger(__name__)


def play_notification_sound(path: Path) -> None:
    """Best-effort sound playback.

    MVP: macOS only via `afplay` (non-blocking). If the file doesn't exist or
    playback fails, we silently ignore.
    """

    try:
        p = Path(path)
        if not p.exists() or not p.is_file():
            return

        if sys.platform == "darwin":
            # Non-blocking; don't use shell=True.
            subprocess.Popen(["afplay", os.fspath(p)])  # noqa: S603,S607
            return

        if sys.platform.startswith("linux"):
            # Try paplay (PulseAudio) first, then aplay (ALSA)
            for player in ("paplay", "aplay"):
                if shutil.which(player):
                    subprocess.Popen([player, os.fspath(p)])
                    return
            return

        if sys.platform.startswith("win"):
            try:
                import winsound

                winsound.PlaySound(str(p), winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception as e:  # noqa: BLE001
                _log.debug("winsound playback failed: %s", e)
            return
        return
    except Exception:  # noqa: BLE001
        _log.debug("Sound playback failed", exc_info=True)
        return
