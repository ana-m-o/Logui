from __future__ import annotations

from pathlib import Path

import tomllib

from logui.ui import app as ui_app


def _pyproject_version() -> str:
    repo_root = Path(__file__).resolve().parents[1]
    pyproject = repo_root / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return str(data.get("project", {}).get("version", "0.0.0"))


def test_get_project_info_prefers_installed_metadata(monkeypatch) -> None:
    monkeypatch.setattr(ui_app.importlib_metadata, "version", lambda _name: "9.9.9")
    name, version = ui_app._get_project_info()
    assert name == "LogUI"
    assert version == "9.9.9"


def test_get_project_info_falls_back_to_pyproject(monkeypatch) -> None:
    def _raise(_name: str) -> str:
        raise ui_app.importlib_metadata.PackageNotFoundError

    monkeypatch.setattr(ui_app.importlib_metadata, "version", _raise)

    name, version = ui_app._get_project_info()
    assert name == "LogUI"
    assert version == _pyproject_version()
