from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


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
                if _which(player):
                    subprocess.Popen([player, os.fspath(p)])
                    return
            return

        if sys.platform.startswith("win"):
            try:
                import winsound
                winsound.PlaySound(str(p), winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception:
                pass
            return
        return
    except Exception:  # noqa: BLE001
        return

def _which(cmd: str) -> str | None:
    """Return the path to an executable or None if not found (like shutil.which, but no import)."""
    for path in os.environ.get("PATH", "").split(os.pathsep):
        exe = os.path.join(path, cmd)
        if os.path.isfile(exe) and os.access(exe, os.X_OK):
            return exe
    return None
