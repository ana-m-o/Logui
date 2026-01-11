from __future__ import annotations

import sys
from pathlib import Path


def test_play_notification_sound_noop_when_missing_file(tmp_path, monkeypatch) -> None:
    from logui.infrastructure.services import sound

    def _popen(*args, **kwargs):  # noqa: ANN001
        raise AssertionError("subprocess.Popen should not be called")

    monkeypatch.setattr(sound.subprocess, "Popen", _popen)

    sound.play_notification_sound(tmp_path / "missing.wav")


def test_play_notification_sound_uses_afplay_on_darwin(tmp_path, monkeypatch) -> None:
    from logui.infrastructure.services import sound

    p = tmp_path / "notification.wav"
    p.write_bytes(b"")

    monkeypatch.setattr(sys, "platform", "darwin")

    calls: list[list[str]] = []

    def _popen(argv, **kwargs):  # noqa: ANN001
        calls.append(list(argv))

        class _Dummy:
            pass

        return _Dummy()

    monkeypatch.setattr(sound.subprocess, "Popen", _popen)

    sound.play_notification_sound(Path(p))
    assert calls == [["afplay", str(p)]]
