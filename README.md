# LogUI

Simple and distraction-free daily planner for the terminal.

The goal of this application is to learn and explore Textual and terminal-based graphical interfaces, focusing on user experience and 100% keyboard-driven operation.

## Features

- **Tasks:** Persistent management with states, priorities, subtasks, notes, optional links, and recurrence (daily/weekly/monthly)
  - Tasks with recurrence automatically clone for the next occurrence when marked as DONE
  - Manual persistent order; when created, tasks/subtasks with due dates are placed at the top by default
- **Events:** Schedule with terminal alerts (toast + local sound), flexible times and recurrence (daily/weekly/monthly)
  - Recurring events automatically clone for the next occurrence during day rollover
  - Monthly recurrence handles edge cases (e.g., day 31 becomes last day of month in February)
- **Log:** Historical view of completed tasks and past events, grouped by date
  - Optional display of journal entries at the end of each day (toggle with checkbox)
- **Journal:** Entries by date with a side history (most recent first) and editor with date change
- **Files:** Management of `.txt` files with a configurable external editor
- **Auto-hide completed items:** Optional setting to automatically hide completed tasks and ended events from today (they move to the Log)
- **Persistent theme:** The app remembers your theme preference when you change it via the command palette (Ctrl+P)
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

By default, LogUI stores data under `~/.logui/` (home directory).

LogUI also supports a **custom data directory**. To make startup reliable (so the app always knows where to find your data), LogUI uses a small **bootstrap** file in the default location:

- `~/.logui/bootstrap.json`: points to the active data directory (when configured)

The *actual* data files live in the active data directory:

- `config.json`: General configuration
- `tasks.json`: Persistent tasks
- `events.json`: Events
- `journal.json`: Journal entries by date
- `files/`: Managed `.txt` files

If you never change the data directory, everything (including `bootstrap.json`) simply lives under `~/.logui/`.

### Changing the data directory

You can change the data directory from inside the app:

1. Open **Config/Help** (`?`)
2. Select **Data directory** and press `e` / `enter`
3. Enter the new path and confirm

When you confirm, LogUI will ask whether you want to migrate existing data to the new directory.

- If you choose **Yes**, LogUI copies existing data files into the new directory.
- If you choose **No**, LogUI will start using the new directory (and write a fresh `config.json` there), but existing data will remain in the old directory.

After changing, LogUI updates `~/.logui/bootstrap.json` so future launches keep using the selected directory.

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
- `r` → Cycle repeat frequency (in Tasks/Events): none → daily → weekly → monthly
- `c` → Cycle task status (in Tasks): todo → in_progress → postponed → in_review → done
- `p` → Toggle priority (in Tasks)
- `a` → Toggle notification (in Events)
- `ctrl+q` → Quit

Notes about Files:

- In Files, `r` renames the selected file.

Notes about the Journal:

- In the Journal editor (multiline), `enter` creates a new line; to save use `ctrl+shift+s`.

## License

GPL-3.0-or-later
