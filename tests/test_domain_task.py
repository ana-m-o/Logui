from __future__ import annotations

from datetime import date

import pytest

from logui.domain.entities import Task, TaskStatus
from logui.domain.entities.task import TaskLink
from logui.domain.errors import ValidationError


def test_task_create_requires_title() -> None:
    with pytest.raises(ValidationError):
        Task.create("")


def test_task_accepts_optional_due_date() -> None:
    t = Task.create("x", due_date=date.today())
    assert t.due_date == date.today()


def test_task_roundtrip_dict() -> None:
    task = Task.create(
        "Comprar leche",
        status=TaskStatus.TODO,
        priority=True,
        due_date=date(2025, 12, 25),
        link=TaskLink.create("https://example.com", text="Ejemplo"),
    )
    task.add_note("Mirar ofertas")

    as_dict = task.to_dict()
    loaded = Task.from_dict(as_dict)

    assert loaded.title == task.title
    assert loaded.status == task.status
    assert loaded.priority == task.priority
    assert loaded.due_date == task.due_date
    assert loaded.link is not None
    assert loaded.link.url == "https://example.com"
    assert loaded.link.text == "Ejemplo"
    assert len(loaded.notes) == 1
    assert loaded.notes[0].text == "Mirar ofertas"
