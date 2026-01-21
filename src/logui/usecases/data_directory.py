"""Use case for changing data directory configuration."""

import logging
import shutil
from pathlib import Path

from logui.domain.entities.config import AppConfig
from logui.domain.ports.config import ConfigRepository

_log = logging.getLogger(__name__)


def ensure_data_dir(path: Path) -> None:
    """Create the data directory if it doesn't exist (best effort)."""
    path.mkdir(parents=True, exist_ok=True)


def set_data_directory(
    repo: ConfigRepository, directory: str, move_files: bool = False, current_dir: Path | None = None
) -> None:
    """Update the data directory in configuration.
    
    Args:
        repo: Configuration repository
        directory: New data directory path (can use ~/ for home)
        move_files: If True, copy existing data files to new location
        current_dir: Current data directory (required if move_files=True)
    """
    current = repo.load()
    # Normalize the path
    normalized = str(directory).strip()
    if not normalized:
        normalized = ""
    
    # Expand the new directory path (if provided)
    new_dir = Path(normalized).expanduser().resolve() if normalized else None
    
    # Move files if requested
    if move_files and current_dir is not None and new_dir is not None:
        current_dir = current_dir.resolve()
        if current_dir != new_dir and current_dir.exists():
            # Create new directory
            new_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy all files except config.json (we'll update that separately)
            for item in current_dir.iterdir():
                if item.name == "config.json":
                    continue  # Don't copy config, we'll save the updated one
                
                dest = new_dir / item.name
                try:
                    if item.is_file():
                        shutil.copy2(item, dest)
                    elif item.is_dir():
                        if dest.exists():
                            shutil.rmtree(dest)
                        shutil.copytree(item, dest)
                except Exception as e:  # noqa: BLE001
                    # Best effort - continue even if some files fail
                    _log.debug("Failed copying %s to %s: %s", item, dest, e)
    
    updated = AppConfig(
        schema_version=current.schema_version,
        editor=current.editor,
        encryption=current.encryption,
        notifications=current.notifications,
        data_directory=normalized or None,
    )
    repo.save(updated)


def get_expanded_data_directory(config: AppConfig, *, fallback: Path | None = None) -> Path:
    """Get the expanded data directory path from config.
    
    Args:
        config: Application configuration
        
    Returns:
        Expanded Path object for the data directory
    """
    raw = (config.data_directory or "").strip()
    if not raw:
        if fallback is not None:
            return fallback.expanduser().resolve()
        return (Path.home() / ".logui").resolve()
    return Path(raw).expanduser().resolve()
