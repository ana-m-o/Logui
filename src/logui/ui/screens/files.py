from __future__ import annotations

import subprocess
from dataclasses import dataclass

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView, Static

from logui.domain.errors import ValidationError
from logui.domain.ports.config import ConfigRepository
from logui.domain.ports.files import FilesRepository
from logui.ui.screens.modals import ConfirmScreen
from logui.usecases.config import update_editor
from logui.usecases.files import (
    build_editor_argv,
    create_txt_file,
    is_gui_editor,
    rename_txt_file,
    resolve_editor_config,
)


@dataclass(frozen=True)
class NewFileResult:
    filename: str


class NewFileScreen(ModalScreen[NewFileResult | None]):
    BINDINGS = [
        Binding("enter", "submit", "Crear", show=False),
        Binding("escape", "cancel", "Cancelar", show=False),
    ]

    def __init__(self, *, initial: str = ""):
        super().__init__()
        self._initial = initial
        self.add_class("modal")

    def compose(self) -> ComposeResult:
        yield Container(
            Label("New file", classes="modal_title"),
            Static("[dim]enter creates • esc cancel[/dim]", classes="modal_help"),
            Label("Name *"),
            Input(
                value=self._initial,
                placeholder="note.txt ('.txt' will be added if missing)",
                id="new_file_name",
            ),
            Static("", id="new_file_error", classes="modal_error"),
            id="new_file",
            classes="modal_box modal_w60",
        )

    def on_mount(self) -> None:
        self.query_one("#new_file_name", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        self._submit()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "new_file_name":
            self._submit()

    def _submit(self) -> None:
        error = self.query_one("#new_file_error", Static)
        error.update("")
        
        # Clear all error classes first
        for input_widget in self.query(Input):
            input_widget.remove_class("error")
        
        new_file_input = self.query_one("#new_file_name", Input)
        name = (new_file_input.value or "").strip()
        
        if not name:
            new_file_input.add_class("error")
            error.update("[red]• El nombre no puede estar vacío[/red]")
            return
        self.dismiss(NewFileResult(filename=name))


@dataclass(frozen=True)
class RenameFileResult:
    new_name: str


class RenameFileScreen(ModalScreen[RenameFileResult | None]):
    BINDINGS = [
        Binding("enter", "submit", "Renombrar", show=False),
        Binding("escape", "cancel", "Cancelar", show=False),
    ]

    def __init__(self, *, current_name: str):
        super().__init__()
        self._current_name = current_name
        self.add_class("modal")

    def compose(self) -> ComposeResult:
        initial = self._current_name
        if initial.lower().endswith(".txt"):
            initial = initial[:-4]

        yield Container(
            Label("Rename file", classes="modal_title"),
            Static("[dim]enter renames • esc cancel[/dim]", classes="modal_help"),
            Label(f"Current: {self._current_name}"),
            Label("New name *"),
            Input(
                value=initial,
                placeholder="new-name.txt ('.txt' will be added if missing)",
                id="rename_file_name",
            ),
            Static("", id="rename_file_error", classes="modal_error"),
            id="rename_file",
            classes="modal_box modal_w60",
        )

    def on_mount(self) -> None:
        self.query_one("#rename_file_name", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        self._submit()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "rename_file_name":
            self._submit()

    def _submit(self) -> None:
        error = self.query_one("#rename_file_error", Static)
        error.update("")

        for input_widget in self.query(Input):
            input_widget.remove_class("error")

        inp = self.query_one("#rename_file_name", Input)
        name = (inp.value or "").strip()
        if not name:
            inp.add_class("error")
            error.update("[red]• El nombre no puede estar vacío[/red]")
            return

        self.dismiss(RenameFileResult(new_name=name))


class FileItem(ListItem):
    def __init__(self, filename: str):
        super().__init__()
        self.filename = filename

    def compose(self) -> ComposeResult:
        yield Static(self.filename, markup=False)


class FilesListView(ListView):
    BINDINGS = [
        Binding("e", "open", "Edit", show=False),
    ]

    def action_open(self) -> None:
        # Route to the pane action.
        try:
            pane = self.app.query_one("#files", FilesPane)
            pane.action_open()
        except Exception as e:  # noqa: BLE001
            try:
                pane._notify_error("Error en acción de abrir", e)
            except Exception:  # noqa: BLE001
                pass


class FilesPane(Container):
    BINDINGS = [
        Binding("enter", "open", "Edit", show=False, priority=True),
        Binding("e", "open", "Edit", show=False, priority=True),
        Binding("n", "new", "New", show=False),
        Binding("x", "delete", "Delete", show=False),
        Binding("r", "rename", "Rename", show=False),
    ]

    def __init__(self, repo: FilesRepository, config_repo: ConfigRepository):
        super().__init__(id="files")
        self._repo = repo
        self._config_repo = config_repo
        self._filenames: list[str] = []

    def compose(self) -> ComposeResult:
        yield Container(
            Horizontal(Label("Files"), classes="page_header"),
            Static(
                "[dim]e/enter edit • n new • r rename • x delete[/dim]",
                classes="page_help",
            ),
            FilesListView(id="files_list", classes="files_list"),
        )

    def on_mount(self) -> None:
        self._refresh()
        try:
            self.query_one("#files_list", ListView).focus()
        except Exception:  # noqa: BLE001
            pass

    def _notify(self, message: str) -> None:
        notify = getattr(self.app, "notify", None)
        if callable(notify):
            notify(message)

    def _notify_error(self, message: str, exc: Exception | None = None) -> None:
        notify = getattr(self.app, "notify", None)
        if not callable(notify):
            return

        if exc is not None:
            try:
                log = getattr(self.app, "log", None)
                if callable(log):
                    log(message, exc=exc)
            except Exception:  # noqa: BLE001
                pass

        full = message
        if exc is not None:
            details = str(exc).strip()
            if details:
                full = f"{message}: {details}"

        try:
            notify(full, title="Error", timeout=30)
        except Exception:  # noqa: BLE001
            try:
                from rich.text import Text

                notify(Text(full), title="Error", timeout=30)
            except Exception:  # noqa: BLE001
                pass

    def _selected_filename(self) -> str | None:
        if not self._filenames:
            return None

        try:
            lv = self.query_one("#files_list", ListView)
        except Exception:  # noqa: BLE001
            return None

        idx = lv.index if lv.index is not None else 0
        if 0 <= idx < len(self._filenames):
            return self._filenames[idx]

        # Defensive fallback (shouldn't be needed, but helps if ListView state
        # briefly desyncs).
        try:
            item = lv.highlighted_child
            if isinstance(item, FileItem):
                return item.filename
        except Exception:  # noqa: BLE001
            pass

        return None

    def action_refresh(self) -> None:
        self._refresh()

    def action_rename(self) -> None:
        filename = self._selected_filename()
        if not filename:
            return

        screen = RenameFileScreen(current_name=filename)

        def _on_done(res: RenameFileResult | None) -> None:
            if res is None:
                return

            try:
                new_name = rename_txt_file(self._repo, filename, res.new_name)
            except ValidationError as e:
                self._notify_error("Error de validación", e)
                return
            except Exception as e:  # noqa: BLE001
                self._notify_error("Error renombrando archivo", e)
                return

            if new_name == filename:
                return

            self._notify("Archivo renombrado")
            self._refresh(keep=new_name)

        self.app.push_screen(screen, callback=_on_done)

    def _refresh(self, *, keep: str | None = None) -> None:
        lv = self.query_one("#files_list", ListView)

        keep_name = keep or self._selected_filename()
        old_index = lv.index if lv.index is not None else 0

        try:
            new_filenames = list(self._repo.list_txt_files())
        except Exception:  # noqa: BLE001
            new_filenames = []

        def _set_selection() -> None:
            if not new_filenames:
                lv.index = 0
                return
            if keep_name and keep_name in new_filenames:
                lv.index = new_filenames.index(keep_name)
            else:
                lv.index = min(max(old_index, 0), len(new_filenames) - 1)

        def _rebuild() -> None:
            lv.clear()
            if not new_filenames:
                lv.append(ListItem(Label("(Sin archivos) — pulsa n para crear")))
                return
            for name in new_filenames:
                lv.append(FileItem(name))

        # Fast-path: no list changes and the DOM looks consistent.
        if new_filenames == self._filenames:
            file_items = [c for c in lv.children if isinstance(c, FileItem)]
            has_non_file_items = any(not isinstance(c, FileItem) for c in lv.children)
            consistent_empty = (not new_filenames) and (not file_items) and has_non_file_items
            consistent_non_empty = (
                bool(new_filenames)
                and (len(file_items) == len(new_filenames))
                and (not has_non_file_items)
            )
            if consistent_empty or consistent_non_empty:
                _set_selection()
                return

        try:
            # Empty state: remove any existing items and show the placeholder.
            if not new_filenames:
                for child in list(lv.children):
                    try:
                        child.remove()
                    except Exception:  # noqa: BLE001
                        pass
                lv.append(ListItem(Label("(Sin archivos) — pulsa n para crear")))
                self._filenames = []
                lv.index = 0
                return

            # Non-empty: remove placeholders (if any) and then apply a minimal diff.
            for child in list(lv.children):
                if not isinstance(child, FileItem):
                    try:
                        child.remove()
                    except Exception:  # noqa: BLE001
                        pass

            current_by_name: dict[str, FileItem] = {
                item.filename: item
                for item in lv.children
                if isinstance(item, FileItem)
            }

            previous_item: FileItem | None = None
            for name in new_filenames:
                item = current_by_name.get(name)
                if item is None:
                    item = FileItem(name)
                    lv.append(item)

                if previous_item is None:
                    if lv.children and lv.children[0] is not item:
                        lv.move_child(item, before=0)
                else:
                    lv.move_child(item, after=previous_item)
                previous_item = item

            new_set = set(new_filenames)
            for name, item in current_by_name.items():
                if name not in new_set:
                    try:
                        item.remove()
                    except Exception:  # noqa: BLE001
                        pass

        except Exception as e:  # noqa: BLE001
            # If the incremental update fails for any reason, fall back to a full rebuild.
            self._notify_error("Error refrescando lista", e)
            _rebuild()

        self._filenames = new_filenames
        _set_selection()

    def on_click(self, event: events.Click) -> None:
        if event.chain < 2 or event.button != 1:
            return

        w = event.widget
        while w is not None and not isinstance(w, ListItem):
            w = getattr(w, "parent", None)
        if w is None:
            return

        list_view = getattr(w, "parent", None)
        while list_view is not None and not isinstance(list_view, ListView):
            list_view = getattr(list_view, "parent", None)
        if list_view is None:
            return

        if getattr(list_view, "id", None) != "files_list":
            return

        list_view.focus()
        self.call_later(self.action_open)

    def action_new(self) -> None:
        screen = NewFileScreen()

        def _on_done(res: NewFileResult | None) -> None:
            if res is None:
                return
            try:
                created = create_txt_file(self._repo, res.filename)
            except ValidationError as e:
                self._notify_error("Error de validación", e)
                return
            except Exception as e:  # noqa: BLE001
                self._notify_error("Error creando archivo", e)
                return

            self._notify("Archivo creado")
            self._refresh(keep=created)

        self.app.push_screen(screen, callback=_on_done)

    def action_delete(self) -> None:
        filename = self._selected_filename()
        if not filename:
            return

        def _on_confirm(ok: bool) -> None:
            if not ok:
                return
            try:
                deleted = self._repo.delete_txt_file(filename)
            except Exception as e:  # noqa: BLE001
                self._notify_error("Error borrando archivo", e)
                return
            if deleted:
                self._notify("Archivo borrado")
            self._refresh()

        self.app.push_screen(ConfirmScreen(f"¿Borrar {filename}?"), callback=_on_confirm)

    def action_open(self) -> None:
        filename = self._selected_filename()
        if not filename:
            return

        try:
            cfg = self._config_repo.load()
            path = self._repo.path_for(filename)
            resolved = resolve_editor_config(cfg.editor)
            if (
                resolved.command != cfg.editor.command
                or resolved.normalized_args() != cfg.editor.normalized_args()
            ):
                # Persist the chosen editor so the user doesn't hit this again.
                args_text = " ".join(resolved.normalized_args())
                update_editor(repo=self._config_repo, command=resolved.command, args_text=args_text)
                msg = (
                    f"Editor no encontrado. Se usará '{resolved.command}' "
                    "(puedes cambiarlo en Config)"
                )
                self._notify(msg)

            argv = build_editor_argv(resolved, path)
            
            # Determine if this is a GUI editor that launches in a separate window
            # vs a terminal editor that needs exclusive terminal access.
            is_gui = is_gui_editor(resolved.command)
            
            # Important: Textual runs the terminal in raw mode and captures input.
            # For TUI editors (nano/vim/etc.) we must suspend the app and run them
            # in the foreground. For GUI editors we launch them without suspending.
            try:
                if is_gui:
                    # Non-blocking: launch GUI editor and continue
                    subprocess.Popen(argv)  # noqa: S603
                else:
                    # Blocking: suspend app and run terminal editor
                    with self.app.suspend():
                        subprocess.run(argv, check=False)  # noqa: S603
            except Exception:  # noqa: BLE001
                # In headless/test drivers suspend may not be available.
                if is_gui:
                    subprocess.Popen(argv)  # noqa: S603
                else:
                    subprocess.run(argv, check=False)  # noqa: S603
        except Exception as e:  # noqa: BLE001
            self._notify_error("Error abriendo editor", e)
