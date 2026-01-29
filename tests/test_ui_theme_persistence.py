"""Tests for theme persistence functionality."""
from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Static

from logui.infrastructure.repositories.config_repo_json import JsonConfigRepository


class ThemeTestApp(App[None]):
    """Test app with config repo."""

    def __init__(self, config_repo, **kwargs):
        super().__init__(**kwargs)
        self._config_repo = config_repo

    def compose(self) -> ComposeResult:
        yield Static("theme test", id="root")
    
    def on_mount(self) -> None:
        """Load saved theme on mount."""
        config = self._config_repo.load()
        if config.ui.theme:
            try:
                self.theme = config.ui.theme
            except Exception:  # noqa: BLE001
                pass
    
    def watch_theme(self, theme_name: str) -> None:
        """Watch theme changes and persist them to config."""
        from logui.usecases.config import set_theme
        try:
            set_theme(repo=self._config_repo, theme_name=theme_name)
        except Exception:  # noqa: BLE001
            pass


def test_theme_is_persisted_on_change(tmp_path: Path) -> None:
    """When the user changes theme via command palette, it should be saved to config."""
    config_repo = JsonConfigRepository(tmp_path / "config.json")

    async def _run() -> None:
        app = ThemeTestApp(config_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            # Change theme programmatically (simulating user selection from command palette)
            app.theme = "nord"
            await pilot.pause()

            # Verify theme was persisted
            reloaded_config = config_repo.load()
            assert reloaded_config.ui.theme == "nord"

    asyncio.run(_run())


def test_theme_is_loaded_on_startup(tmp_path: Path) -> None:
    """When app starts, it should load the previously saved theme."""
    config_repo = JsonConfigRepository(tmp_path / "config.json")

    # Save a theme preference
    from logui.usecases.config import set_theme
    set_theme(repo=config_repo, theme_name="gruvbox")

    async def _run() -> None:
        app = ThemeTestApp(config_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            # Verify theme was applied on mount
            assert app.theme == "gruvbox"

    asyncio.run(_run())


def test_theme_changes_are_tracked(tmp_path: Path) -> None:
    """Multiple theme changes should be persisted correctly."""
    config_repo = JsonConfigRepository(tmp_path / "config.json")

    async def _run() -> None:
        app = ThemeTestApp(config_repo)
        async with app.run_test() as pilot:
            await pilot.pause()

            # Change theme multiple times
            app.theme = "nord"
            await pilot.pause()

            reloaded_config = config_repo.load()
            assert reloaded_config.ui.theme == "nord"

            app.theme = "tokyo-night"
            await pilot.pause()

            reloaded_config = config_repo.load()
            assert reloaded_config.ui.theme == "tokyo-night"

    asyncio.run(_run())


def test_default_theme_is_none(tmp_path: Path) -> None:
    """When no theme has been set, config should have theme=None."""
    config_repo = JsonConfigRepository(tmp_path / "config.json")
    
    config = config_repo.load()
    assert config.ui.theme is None
