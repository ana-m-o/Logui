from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

from logui.domain import recurrence as rec
from logui.domain.errors import ValidationError


class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    POSTPONED = "postponed"
    IN_REVIEW = "in_review"
    DONE = "done"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class TaskLink:
    url: str
    text: str | None = None

    @staticmethod
    def create(url: str, *, text: str | None = None) -> "TaskLink":
        cleaned_url = (url or "").strip()
        cleaned_text = (text or "").strip() or None

        if not cleaned_url:
            raise ValidationError("Link url cannot be empty")

        parsed = urlparse(cleaned_url)
        if not parsed.scheme:
            raise ValidationError("Link url must include a scheme (e.g. https://)")
        if parsed.scheme in {"http", "https"} and not parsed.netloc:
            raise ValidationError("Invalid http(s) url")

        return TaskLink(url=cleaned_url, text=cleaned_text)

    def display_text(self) -> str:
        return (self.text or "").strip() or self.url

    def to_dict(self) -> dict[str, Any]:
        return {"url": self.url, "text": self.text}

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "TaskLink":
        try:
            return TaskLink.create(str(data.get("url") or ""), text=(data.get("text") or None))
        except (TypeError, ValueError) as e:
            raise ValidationError(f"Invalid TaskLink: {e}") from e


@dataclass(frozen=True)
class TaskNote:
    id: UUID
    text: str
    created_at: datetime

    @staticmethod
    def create(
        text: str, *, now: datetime | None = None, note_id: UUID | None = None
    ) -> "TaskNote":
        cleaned = (text or "").strip()
        if not cleaned:
            raise ValidationError("Note text cannot be empty")
        return TaskNote(id=note_id or uuid4(), text=cleaned, created_at=now or utc_now())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "text": self.text,
            "created_at": self.created_at.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "TaskNote":
        try:
            created_at = _parse_dt_utc(data["created_at"])
            return TaskNote(id=UUID(data["id"]), text=str(data["text"]), created_at=created_at)
        except (KeyError, TypeError, ValueError) as e:
            raise ValidationError(f"Invalid TaskNote: {e}") from e


@dataclass
class Task:
    id: UUID
    order: int
    title: str
    status: TaskStatus
    priority: bool
    due_date: date | None
    link: TaskLink | None = None
    repeat: dict[str, Any] | None = None
    notes: list[TaskNote] = field(default_factory=list)
    subtasks: list["Task"] = field(default_factory=list)
    completed_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @staticmethod
    def create(
        title: str,
        *,
        now: datetime | None = None,
        task_id: UUID | None = None,
        order: int = 0,
        status: TaskStatus = TaskStatus.TODO,
        priority: bool = False,
        due_date: date | None = None,
        link: TaskLink | None = None,
        repeat: dict[str, Any] | None = None,
    ) -> "Task":
        cleaned = (title or "").strip()
        if not cleaned:
            raise ValidationError("Task title cannot be empty")
        ts = now or utc_now()
        completed_at: datetime | None = ts if status == TaskStatus.DONE else None
        return Task(
            id=task_id or uuid4(),
            order=int(order),
            title=cleaned,
            status=status,
            priority=bool(priority),
            due_date=due_date,
            link=link,
            repeat=repeat,
            completed_at=completed_at,
            created_at=ts,
            updated_at=ts,
        )

    def touch(self, *, now: datetime | None = None) -> None:
        self.updated_at = now or utc_now()

    def add_note(self, text: str, *, now: datetime | None = None) -> TaskNote:
        note = TaskNote.create(text, now=now)
        self.notes.append(note)
        self.touch(now=now)
        return note

    def add_subtask(self, subtask: "Task", *, now: datetime | None = None) -> None:
        self.subtasks.append(subtask)
        self.touch(now=now)

    def occurs_on(self, target: date) -> bool:
        """Check if this task has an occurrence on the target date.

        For tasks with due_date, check if the occurrence falls on that date.
        If no due_date, recurring tasks occur every interval starting from created date.
        """
        if not self.due_date:
            # No due date: can't determine occurrences
            return False
        return rec.occurs_on_date(self.due_date, self.repeat, target)

    def next_occurrence(self, after: date) -> date | None:
        """Get the next occurrence after the given date."""
        if not self.due_date:
            return None
        return rec.next_occurrence(self.due_date, self.repeat, after)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "order": self.order,
            "title": self.title,
            "status": self.status.value,
            "priority": self.priority,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "link": self.link.to_dict() if self.link else None,
            "repeat": self.repeat,
            "notes": [n.to_dict() for n in self.notes],
            "subtasks": [t.to_dict() for t in self.subtasks],
            "completed_at": _format_dt_utc(self.completed_at) if self.completed_at else None,
            "created_at": _format_dt_utc(self.created_at),
            "updated_at": _format_dt_utc(self.updated_at),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Task":
        try:
            order = int(data.get("order", 0))
            due_date = date.fromisoformat(data["due_date"]) if data.get("due_date") else None

            link: TaskLink | None = None
            raw_link = data.get("link")
            if isinstance(raw_link, dict):
                link = TaskLink.from_dict(raw_link)

            created_at = _parse_dt_utc(data["created_at"])
            updated_at = _parse_dt_utc(data["updated_at"])

            completed_at: datetime | None = None
            if data.get("completed_at"):
                completed_at = _parse_dt_utc(data["completed_at"])

            task = Task(
                id=UUID(data["id"]),
                order=order,
                title=str(data["title"]),
                status=TaskStatus(data["status"]),
                priority=bool(data.get("priority", False)),
                due_date=due_date,
                link=link,
                repeat=data.get("repeat"),
                notes=[TaskNote.from_dict(n) for n in (data.get("notes") or [])],
                subtasks=[Task.from_dict(t) for t in (data.get("subtasks") or [])],
                completed_at=completed_at,
                created_at=created_at,
                updated_at=updated_at,
            )

            task._validate_invariants()  # noqa: SLF001
            return task
        except ValidationError:
            raise
        except (KeyError, TypeError, ValueError) as e:
            raise ValidationError(f"Invalid Task: {e}") from e

    def _validate_invariants(self) -> None:
        if not (self.title or "").strip():
            raise ValidationError("Task title cannot be empty")
        if self.order < 0:
            raise ValidationError("Task order must be >= 0")
        if self.link is not None:
            # Ensure persisted objects still validate.
            TaskLink.create(self.link.url, text=self.link.text)

        if self.status == TaskStatus.DONE:
            if self.completed_at is None:
                raise ValidationError("completed_at is required when status is done")
        else:
            if self.completed_at is not None:
                raise ValidationError("completed_at must be null unless status is done")


def _format_dt_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_dt_utc(raw: Any) -> datetime:
    if not isinstance(raw, str):
        raise ValueError("datetime must be a string")
    s = raw.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
