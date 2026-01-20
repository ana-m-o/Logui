"""Main Textual application."""

import sys
from datetime import date, datetime
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib  # type: ignore[import-not-found,no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import ContentSwitcher, Footer, Header, ListItem, ListView, Static

from logui.infrastructure.repositories.config_repo_json import JsonConfigRepository
from logui.infrastructure.repositories.bootstrap_repo_json import JsonBootstrapRepository
from logui.infrastructure.repositories.events_repo_json import JsonEventRepository
from logui.infrastructure.repositories.files_repo_fs import FsFilesRepository
from logui.infrastructure.repositories.journal_repo_json import JsonJournalRepository
from logui.infrastructure.repositories.tasks_repo_json import JsonTaskRepository
from logui.infrastructure.services.sound import play_notification_sound
from logui.ui.dates import fmt_day_header_en
from logui.ui.screens.config import ConfigPane
from logui.ui.screens.events import EventsPane, ensure_data_dir
from logui.ui.screens.files import FilesPane
from logui.ui.screens.journal import JournalPane
from logui.ui.screens.log import LogPane
from logui.ui.screens.tasks import TasksPane
from logui.usecases.event_notifications import (
    DEFAULT_ALL_DAY_NOTIFY_TIME,
    due_notifications,
    notification_key,
)
from logui.usecases.data_directory import get_expanded_data_directory
from logui.domain.entities.bootstrap import BootstrapConfig
from logui.domain.entities.config import AppConfig


def _get_project_info() -> tuple[str, str]:
    """Read project name and version from pyproject.toml."""
    try:
        if tomllib is None:
            return ("LogUI", "0.0.0")
        
        # Find pyproject.toml relative to this file
        current_file = Path(__file__)
        project_root = current_file.parents[3]  # logui/ui/app.py -> src -> code -> project root
        pyproject_path = project_root / "pyproject.toml"
        
        if not pyproject_path.exists():
            return ("LogUI", "0.0.0")
        
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
            project = data.get("project", {})
            name = project.get("name", "LogUI")
            version = project.get("version", "0.0.0")
            # Capitalize first letter if needed (logui -> LogUI)
            if name.lower() == "logui":
                name = "LogUI"
            return (name, version)
    except Exception:  # noqa: BLE001
        return ("LogUI", "0.0.0")


class NavItem(ListItem):
    def __init__(self, label: str, screen_id: str):
        super().__init__(id=screen_id, classes="menu_item")
        self.screen_id = screen_id
        self._base_label = label

    def compose(self) -> ComposeResult:
        yield Static(self._base_label, markup=True, id=f"nav_label_{self.screen_id}")
    
    def update_label(self, text: str) -> None:
        """Update the navigation item label."""
        try:
            label = self.query_one(f"#nav_label_{self.screen_id}", Static)
            label.update(text)
        except Exception:  # noqa: BLE001
            pass


class Sidebar(Container):
    """Navigation sidebar."""

    def compose(self) -> ComposeResult:
        with ListView(id="nav-list"):
            yield NavItem("Tasks", "tasks")
            yield NavItem("Events", "events")
            yield NavItem("Journal", "journal")
            yield NavItem("Files", "files")
            yield NavItem("Log", "log")
            yield NavItem("Config/Help", "config")


class LogUIApp(App):
    """TUI de productividad LogUI."""
    
    CSS_PATH = [
        "styles/app.tcss",
    ]

    BINDINGS = [
        ("t", "nav_tasks", "Tasks"),
        ("v", "nav_events", "Events"),
        ("j", "nav_journal", "Journal"),
        ("f", "nav_files", "Files"),
        ("l", "nav_log", "Log"),
        ("?", "nav_config", "Config/Help"),
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        name, _version = _get_project_info()
        self.title = name

        # Bootstrap: keep a tiny bootstrap.json in the default directory so the app
        # can discover the user-configured data directory on startup.
        default_dir = self._default_data_dir()
        ensure_data_dir(default_dir)
        self._bootstrap_repo = JsonBootstrapRepository(default_dir / "bootstrap.json")
        bootstrap = self._bootstrap_repo.load()

        # Data directory (events/tasks/journal/files + full config)
        # If bootstrap has no override, fall back to default_dir (important for tests).
        self._data_dir = (
            Path(bootstrap.data_directory).expanduser().resolve()
            if bootstrap.data_directory
            else default_dir.expanduser().resolve()
        )
        ensure_data_dir(self._data_dir)

        # Full config lives inside the data directory.
        self._config_repo = JsonConfigRepository(self._data_dir / "config.json")
        config = self._config_repo.load()

        # Backward/compat: if old config had data_directory set, prefer it and
        # write it to bootstrap so future startups use it.
        legacy_dir = get_expanded_data_directory(config, fallback=self._data_dir)
        if legacy_dir != self._data_dir:
            self._data_dir = legacy_dir
            ensure_data_dir(self._data_dir)
            self._bootstrap_repo.save(BootstrapConfig(data_directory=str(legacy_dir)))
            self._config_repo = JsonConfigRepository(self._data_dir / "config.json")
            config = self._config_repo.load()

        files_dir = self._data_dir / "files"
        files_dir.mkdir(parents=True, exist_ok=True)
        self._events_repo = JsonEventRepository(self._data_dir / "events.json")
        self._tasks_repo = JsonTaskRepository(self._data_dir / "tasks.json")
        self._journal_repo = JsonJournalRepository(self._data_dir / "journal.json")
        self._files_repo = FsFilesRepository(files_dir)
        self._sent_notification_keys: set[str] = set()
        logui_dir = Path(__file__).resolve().parents[1]
        self._notify_sound_path = logui_dir / "assets" / "sounds" / "notification.wav"

        # Track local day while the app is running to perform a daily rollover
        # without requiring a restart.
        self._ui_day: date = datetime.now().date()
        self._poll_counter: int = 0  # Counter for 30-second tasks

    def change_data_directory(self, *, new_dir: str, move_files: bool) -> bool:
        """Update bootstrap data dir and copy data/config as requested.

        Returns True if the change was applied, False if it was a no-op.
        """
        raw = (new_dir or "").strip()
        if not raw:
            return False

        current_dir = self._data_dir.expanduser().resolve()
        target_dir = Path(raw).expanduser().resolve()
        if target_dir == current_dir:
            return False

        target_dir.mkdir(parents=True, exist_ok=True)

        # Always move/copy the *full config* to the new data directory.
        # This is approach (1): the data directory contains the real config.
        try:
            current_config = self._config_repo.load()
            # Ensure we don't keep a recursive override in the full config.
            cleaned_config = AppConfig(
                schema_version=current_config.schema_version,
                editor=current_config.editor,
                encryption=current_config.encryption,
                notifications=current_config.notifications,
                data_directory=None,
            )
            JsonConfigRepository(target_dir / "config.json").save(cleaned_config)
        except Exception:  # noqa: BLE001
            pass

        if move_files:
            # Copy everything from current data dir into the new dir, but keep
            # the target config.json we just wrote (settings should come along).
            for item in current_dir.iterdir():
                if item.name == "config.json":
                    continue
                dest = target_dir / item.name
                try:
                    if item.is_file():
                        import shutil

                        shutil.copy2(item, dest)
                    elif item.is_dir():
                        import shutil

                        if dest.exists():
                            shutil.rmtree(dest)
                        shutil.copytree(item, dest)
                except Exception:  # noqa: BLE001
                    pass

        # Update bootstrap pointer.
        self._bootstrap_repo.save(BootstrapConfig(data_directory=str(target_dir)))
        return True

    def compose(self) -> ComposeResult:
        """Create widgets."""
        yield Header(show_clock=True)
        with Horizontal(id="layout"):
            yield Sidebar(id="sidebar")

            with Container(id="main"):
                yield ContentSwitcher(
                    TasksPane(self._tasks_repo),
                    EventsPane(self._events_repo),
                    JournalPane(self._journal_repo),
                    FilesPane(self._files_repo, self._config_repo),
                    LogPane(self._events_repo, self._tasks_repo),
                    ConfigPane(self._config_repo, data_dir_text=str(self._data_dir)),
                    id="content",
                    initial="tasks",
                )
        yield Footer()

    def on_mount(self) -> None:
        self._set_active("tasks")
        self._update_header_date()
        self.update_nav_counts()  # Initial update
        self._start_polling()

    def format_title(self, title: str, sub_title: str) -> str:
        now = datetime.now()
        date_s = fmt_day_header_en(now.date())
        _name, version = _get_project_info()

        base = (title or "").strip() or "LogUI"
        return f"[dim]{base} v{version}[/dim] · {date_s}"

    def _update_header_date(self, now: datetime | None = None) -> None:
        dt = now or datetime.now()
        # Show the current date in the header (left side) and keep it fresh on rollover.
        try:
            self.sub_title = fmt_day_header_en(dt.date())
        except Exception:  # noqa: BLE001
            pass

    def _start_polling(self) -> None:
        """Start unified polling for all periodic tasks."""
        try:
            self.set_interval(15, self._poll)
            self._poll_event_notifications()  # Run notifications immediately
        except Exception:  # noqa: BLE001
            pass
    
    def _poll(self) -> None:
        """Unified polling function called every 15 seconds."""
        self._poll_counter += 1
        
        # Every 15 seconds: check event notifications
        self._poll_event_notifications()
        
        # Every 30 seconds (every 2nd call): check day rollover and update counts
        if self._poll_counter % 2 == 0:
            self._poll_day_rollover()
            self.update_nav_counts()
    
    def update_nav_counts(self) -> None:
        """Update navigation item labels with counts. Public method."""
        try:
            count = self._count_today_events()
            nav_item = self.query_one("#events", NavItem)
            if count > 0:
                nav_item.update_label(f"Events [dim]({count})[/dim]")
            else:
                nav_item.update_label("Events")
        except Exception:  # noqa: BLE001
            pass
    
    def _count_today_events(self) -> int:
        """Count events for today, including multi-day events in progress."""
        try:
            from datetime import datetime, time as dt_time
            now = datetime.now()
            today = now.date()
            events = self._events_repo.list_events()
            count = 0
            for ev in events:
                # Calculate end day
                end_day = ev.date.fromordinal(ev.date.toordinal() + int(ev.end_day_offset or 0))
                
                # Skip if event ended before today
                if end_day < today:
                    continue
                
                # Skip if event starts after today
                if ev.date > today:
                    continue
                
                # Event is within date range (started on or before today, ends on or after today)
                # Now check if it has already finished based on time
                if end_day == today and ev.end_time is not None:
                    # Event ends today with a specific time - check if it already passed
                    end_datetime = datetime.combine(end_day, ev.end_time)
                    if now >= end_datetime:
                        continue  # Event already finished
                
                count += 1
            return count
        except Exception:  # noqa: BLE001
            return 0

    def _poll_day_rollover(self) -> None:
        now = datetime.now()
        today = now.date()
        if today == self._ui_day:
            return

        self._ui_day = today
        self._update_header_date(now)
        self._day_rollover(today=today)

    def _day_rollover(self, *, today: date) -> None:
        # Best-effort: ask panes to refresh their date-dependent filtering.
        try:
            self.query_one("#tasks").on_day_rollover(today=today)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
        try:
            self.query_one("#events").on_day_rollover(today=today)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
        try:
            self.query_one("#log").on_day_rollover(today=today)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass

    def _poll_event_notifications(self) -> None:
        now = datetime.now()
        try:
            events = list(self._events_repo.list_events())
        except Exception:  # noqa: BLE001
            return

        # Load config on each poll so edits in Config/Help apply immediately.
        try:
            cfg = self._config_repo.load()
            all_day_time = cfg.notifications.parsed_all_day_notify_time()
            default_minutes_before = int(cfg.notifications.default_minutes_before)
            if default_minutes_before < 0:
                default_minutes_before = 0
        except Exception:  # noqa: BLE001
            all_day_time = DEFAULT_ALL_DAY_NOTIFY_TIME
            default_minutes_before = 0

        due = due_notifications(
            events,
            now=now,
            already_sent=self._sent_notification_keys,
            default_minutes_before=default_minutes_before,
            all_day_notify_time=all_day_time,
        )
        if not due:
            return

        for n in due:
            key = notification_key(n.event_id, n.due_at)
            self._sent_notification_keys.add(key)

            # Toast in-app
            try:
                if n.minutes_before is not None and n.minutes_before > 0:
                    mins = n.minutes_before
                    unit = "minuto" if mins == 1 else "minutos"
                    toast_title = f"Empieza dentro de {mins} {unit}:"
                else:
                    toast_title = "Empieza ahora:"

                try:
                    self.notify(n.title, title=toast_title, timeout=30)
                except Exception:  # noqa: BLE001
                    # Fallback: avoid markup parsing issues in notification text.
                    from rich.text import Text

                    self.notify(Text(str(n.title)), title=str(toast_title), timeout=30)
            except Exception:  # noqa: BLE001
                pass

            # Custom sound (best effort; non-blocking)
            play_notification_sound(self._notify_sound_path)

    def _default_data_dir(self) -> Path:
        return Path.home() / ".logui"

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id != "nav-list":
            return
        if isinstance(event.item, NavItem):
            self._set_active(event.item.screen_id)

    def _set_active(self, screen_id: str) -> None:
        content = self.query_one("#content", ContentSwitcher)
        content.current = screen_id

        nav = self.query_one("#nav-list", ListView)
        items = list(nav.query(NavItem))
        for idx, item in enumerate(items):
            if item.id == screen_id:
                item.add_class("active")
                nav.index = idx
            else:
                item.remove_class("active")

        self.call_later(self._focus_first_interactive, screen_id)

    def _focus_first_interactive(self, screen_id: str) -> None:
        try:
            if screen_id == "tasks":
                self.query_one("#tasks_list", ListView).focus()
                return
            if screen_id == "events":
                self.query_one("#events_list", ListView).focus()
                return
            if screen_id == "journal":
                self.query_one("#journal_history_list", ListView).focus()
                return
            if screen_id == "files":
                self.query_one("#files_list", ListView).focus()
                return
            if screen_id == "log":
                self.query_one("#log_list", ListView).focus()
                return
            if screen_id == "config":
                self.query_one("#config_list", ListView).focus()
                return
        except Exception:  # noqa: BLE001
            return

    def action_nav_tasks(self) -> None:
        self._set_active("tasks")

    def action_nav_events(self) -> None:
        self._set_active("events")

    def action_nav_journal(self) -> None:
        self._set_active("journal")

    def action_nav_files(self) -> None:
        self._set_active("files")

    def action_nav_log(self) -> None:
        self._set_active("log")

    def action_nav_config(self) -> None:
        self._set_active("config")


def run() -> None:
    """Ejecutar la aplicación."""
    app = LogUIApp()
    app.run()
