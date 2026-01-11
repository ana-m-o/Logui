# LogUI

Simple and distraction-free daily planner for the terminal.

The goal of this application is to learn and explore Textual and terminal-based graphical interfaces, focusing on user experience and 100% keyboard-driven operation.

## Features

- **Tasks:** Persistent management with states, priorities, subtasks, notes, and optional links (manual persistent order; when created, tasks/subtasks with due dates are placed at the top by default)
- **Events:** Schedule with terminal alerts (toast + local sound), flexible times and repetition (coming soon; does not yet expand occurrences)
- **Journal:** Entries by date with a side history (most recent first) and editor with date change
- **Files:** Management of `.txt` files with a configurable external editor
- **100% keyboard:** Navigation and operation fully keyboard-oriented

## Requirements

- Python 3.9 or higher
- macOS, Linux, or Windows

## Installation

To install LogUI and use it with the `logui` command:

```bash
# From the project directory
pip install .

# Or for editable/development mode (recommended for development)
pip install -e .
```

After installation, you can run the app from anywhere:

```bash
logui
```

To update after code changes:

```bash
# If installed normally, reinstall:
pip install --upgrade .

# If installed in editable mode (-e), changes apply automatically
# No reinstall needed
```

To uninstall:

```bash
pip uninstall logui
```

## Development Installation

### With hatch (recommended)

```bash
# Install hatch if you don't have it
pip install hatch

# Install dependencies
hatch env create

# Run the application
hatch run app

# Run tests
hatch run test

# Linting
hatch run lint

# Format code
hatch run format
```

### Without hatch

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Run the application
python -m logui.main

# Run tests
pytest
```

## Persistence

Data is stored in JSON under `~/.logui/` (home directory):

- `config.json`: General configuration
- `tasks.json`: Persistent tasks
- `events.json`: Events
- `journal.json`: Journal entries by date
- `files/`: Managed `.txt` files

Note about the editor: by default, `nano` is used, but if the configured editor does not exist on your system, LogUI will try to detect another available editor (including `VISUAL`/`EDITOR`) and save it in `config.json`.

Encryption is optional and can be enabled from the configuration.

## Main Shortcuts (MVP)

- `t` → Tasks
- `v` → Events (view)
- `j` → Journal
- `f` → Files
- `?` → Config/Help
- `n` → Create new
- `enter` → Edit/confirm
- `e` → Edit/open (in lists)
- `esc` → Cancel
- `x` → Delete
- `alt+↑` / `alt+↓` → Reorder (in Tasks)
- `s` → Create subtask (in Tasks)
- `m` → Notes for the selected item (in Tasks/Events)
- `o` → Open task link (in Tasks, if present)
- `ctrl+q` → Quit

Notes about the Journal:

- In the Journal editor (multiline), `enter` creates a new line; to save use `ctrl+shift+s`.

## License

GPL-3.0-or-later
