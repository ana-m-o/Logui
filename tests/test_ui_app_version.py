from __future__ import annotations

from pathlib import Path

import tomllib

from logui.ui import app as ui_app


def _pyproject_version() -> str:
    repo_root = Path(__file__).resolve().parents[1]
    pyproject = repo_root / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return str(data.get("project", {}).get("version", "0.0.0"))


def test_get_project_info_prefers_source_version_when_metadata_mismatch(monkeypatch) -> None:
    # When running from a repo checkout, an older installed distribution may exist.
    # In that case we should prefer the in-source version over stale installed metadata.
    monkeypatch.setattr(ui_app.importlib_metadata, "version", lambda _name: "9.9.9")
    name, version = ui_app._get_project_info()
    assert name == "LogUI"
    assert version == _pyproject_version()


def test_get_project_info_uses_source_version_when_metadata_missing(monkeypatch) -> None:
    def _raise(_name: str) -> str:
        raise ui_app.importlib_metadata.PackageNotFoundError

    monkeypatch.setattr(ui_app.importlib_metadata, "version", _raise)

    name, version = ui_app._get_project_info()
    assert name == "LogUI"
    assert version == _pyproject_version()


def test_get_project_info_falls_back_to_pyproject_if_source_import_fails(monkeypatch) -> None:
    def _raise(_name: str) -> str:
        raise ui_app.importlib_metadata.PackageNotFoundError

    monkeypatch.setattr(ui_app.importlib_metadata, "version", _raise)

    import builtins

    real_import = builtins.__import__

    def _import(name, globals=None, locals=None, fromlist=(), level=0):  # type: ignore[no-untyped-def]
        if name == "logui" and fromlist and "__version__" in fromlist:
            raise ImportError("blocked for test")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _import)

    name, version = ui_app._get_project_info()
    assert name == "LogUI"
    assert version == _pyproject_version()
