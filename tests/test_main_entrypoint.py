from __future__ import annotations


def test_main_returns_0_on_success(monkeypatch) -> None:
    import logui.main as main_mod

    called: list[bool] = []

    def _run() -> None:
        called.append(True)

    monkeypatch.setattr(main_mod, "run", _run)

    assert main_mod.main() == 0
    assert called == [True]


def test_main_returns_0_on_keyboard_interrupt(monkeypatch) -> None:
    import logui.main as main_mod

    def _run() -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(main_mod, "run", _run)

    assert main_mod.main() == 0


def test_main_returns_1_on_exception(monkeypatch, capsys) -> None:
    import logui.main as main_mod

    def _run() -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(main_mod, "run", _run)

    assert main_mod.main() == 1
    captured = capsys.readouterr()
    assert "Error: boom" in captured.err
