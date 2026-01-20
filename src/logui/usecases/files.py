from __future__ import annotations

import os
import shlex
import shutil
import sys
from pathlib import Path

from logui.domain.entities.config import EditorConfig
from logui.domain.errors import ValidationError
from logui.domain.ports.files import FilesRepository


# GUI editors that launch in separate windows (non-blocking)
# Add editors here to avoid app suspend/resume flicker
GUI_EDITORS = {
    "code",
    "code-insiders",
    "subl",
    "sublime_text",
    "atom",
    "gedit",
    "kate",
    "notepad++",
    "notepad",
    "gvim",
    "idea",
    "pycharm",
    "webstorm",
}


def is_gui_editor(command: str) -> bool:
    """Check if the given editor command is a GUI editor."""
    return command in GUI_EDITORS


def normalize_txt_filename(raw: str) -> str:
    name = (raw or "").strip()
    if not name:
        raise ValidationError("El nombre no puede estar vacío")

    # Disallow path traversal / subdirectories.
    if "/" in name or "\\" in name:
        raise ValidationError("El nombre no puede contener rutas (usa solo el nombre del archivo)")
    if name in {".", ".."} or ".." in name:
        raise ValidationError("Nombre inválido")

    if not name.lower().endswith(".txt"):
        name = name + ".txt"

    # Normalize to basename.
    safe = Path(name).name
    if safe != name:
        raise ValidationError("Nombre inválido")

    return safe


def list_txt_files(repo: FilesRepository) -> list[str]:
    return list(repo.list_txt_files())


def create_txt_file(repo: FilesRepository, raw_name: str) -> str:
    filename = normalize_txt_filename(raw_name)
    try:
        repo.create_txt_file(filename)
    except FileExistsError:
        raise ValidationError("Ya existe ese archivo") from None
    return filename


def delete_txt_file(repo: FilesRepository, filename: str) -> bool:
    filename = normalize_txt_filename(filename)
    return bool(repo.delete_txt_file(filename))


def rename_txt_file(repo: FilesRepository, old_filename: str, new_raw_name: str) -> str:
    old = normalize_txt_filename(old_filename)
    new = normalize_txt_filename(new_raw_name)

    if old == new:
        return new

    try:
        repo.rename_txt_file(old, new)
    except FileNotFoundError:
        raise ValidationError("No existe el archivo") from None
    except FileExistsError:
        raise ValidationError("Ya existe ese archivo") from None

    return new


def build_editor_argv(editor: EditorConfig, file_path: Path) -> list[str]:
    cmd = (editor.command or "nano").strip() or "nano"
    args = editor.normalized_args()

    file_str = str(file_path)
    argv = [cmd]

    if args:
        replaced = [a.replace("{file}", file_str) for a in args]
        argv.extend(replaced)
        if not any("{file}" in a for a in args):
            argv.append(file_str)
    else:
        argv.append(file_str)

    return argv


def resolve_editor_config(
    editor: EditorConfig,
    *,
    env: dict[str, str] | None = None,
    platform: str | None = None,
) -> EditorConfig:
    """Return a usable EditorConfig.

    If the configured editor is not available, try VISUAL/EDITOR and then
    common editors for the current platform.

    Notes:
    - Availability is checked via PATH (shutil.which) when possible.
    - For env vars (VISUAL/EDITOR) we accept formats like "code --wait".
    - If we must fall back to a different editor, args are only preserved for
      VISUAL/EDITOR (because they come as a single string); for hardcoded
      candidates we use known-good defaults.
    """

    env = env or dict(os.environ)
    platform = platform or sys.platform

    def _is_available(cmd: str) -> bool:
        s = (cmd or "").strip()
        if not s:
            return False
        # If it's a path, check directly; otherwise rely on PATH resolution.
        if "/" in s or "\\" in s:
            p = Path(s)
            return p.exists()
        return shutil.which(s) is not None

    def _parse_cmdline(value: str) -> tuple[str, list[str]] | None:
        raw = (value or "").strip()
        if not raw:
            return None
        try:
            parts = shlex.split(raw)
        except Exception:  # noqa: BLE001
            parts = raw.split()
        if not parts:
            return None
        return parts[0], parts[1:]

    # 1) Configured editor (defaulting to nano).
    configured = EditorConfig(
        command=(editor.command or "nano").strip() or "nano",
        args=editor.normalized_args(),
    )
    if _is_available(configured.command):
        return configured

    # 2) VISUAL / EDITOR.
    for var in ("VISUAL", "EDITOR"):
        parsed = _parse_cmdline(env.get(var, ""))
        if not parsed:
            continue
        cmd, args = parsed
        if _is_available(cmd):
            return EditorConfig(command=cmd, args=args)

    # 3) Platform-aware candidates.
    # Prefer terminal editors first.
    candidates: list[tuple[str, list[str] | None]] = [
        ("nano", None),
        ("nvim", None),
        ("vim", None),
        ("vi", None),
        ("micro", None),
        ("emacs", None),
        ("hx", None),
        ("kak", None),
        ("joe", None),
    ]

    # GUI editors that can still work if installed; prefer ones with wait flags.
    candidates.extend(
        [
            ("code", ["--wait"]),
            ("code-insiders", ["--wait"]),
            ("subl", ["-w"]),
        ]
    )

    if platform.startswith("win"):
        # Built-in on Windows.
        candidates.insert(0, ("notepad", None))

    for cmd, args in candidates:
        if _is_available(cmd):
            return EditorConfig(command=cmd, args=list(args or []))

    # Nothing found: return the configured value (even if missing) so callers
    # can produce a meaningful error.
    return configured
