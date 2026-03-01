from __future__ import annotations

import sys
from pathlib import Path

import pytest


def pytest_configure() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src = repo_root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


@pytest.fixture
def sqlite_db(tmp_path: Path):
    """Create an initialized SQLiteDatabase for tests."""
    from logui.infrastructure.persistence.sqlite_database import SQLiteDatabase

    db = SQLiteDatabase(tmp_path / "logui.db")
    db.init_schema()
    yield db
    # Ensure database is closed after each test
    db.close()
