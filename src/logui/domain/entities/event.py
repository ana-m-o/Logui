from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from logui.domain.errors import ValidationError


class RepeatFreq(str, Enum):
    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class EventNote:
    id: UUID
    text: str
    created_at: datetime

    @staticmethod
    def create(
        text: str,
        *,
        now: datetime | None = None,
        note_id: UUID | None = None,
    ) -> "EventNote":
        cleaned = (text or "").strip()
        if not cleaned:
            raise ValidationError("Note text cannot be empty")
        return EventNote(id=note_id or uuid4(), text=cleaned, created_at=now or utc_now())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "text": self.text,
            "created_at": _format_dt_utc(self.created_at),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "EventNote":
        try:
            return EventNote(
                id=UUID(data["id"]),
                text=str(data["text"]),
                created_at=_parse_dt_utc(data["created_at"]),
            )
        except (KeyError, TypeError, ValueError) as e:
            raise ValidationError(f"Invalid EventNote: {e}") from e


@dataclass
class Event:
    id: UUID
    title: str
    date: date
    start_time: time | None
    end_time: time | None
    end_day_offset: int
    notify: bool
    notify_minutes_before: int | None
    repeat: dict[str, Any] | None
    notes: list[EventNote] = field(default_factory=list)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @staticmethod
    def create(
        title: str,
        *,
        day: date,
        now: datetime | None = None,
        event_id: UUID | None = None,
        start_time: time | None = None,
        end_time: time | None = None,
        end_day_offset: int = 0,
        notify: bool = True,
        notify_minutes_before: int | None = None,
        repeat: dict[str, Any] | None = None,
    ) -> "Event":
        cleaned = (title or "").strip()
        if not cleaned:
            raise ValidationError("Event title cannot be empty")

        if not isinstance(end_day_offset, int) or end_day_offset < 0:
            raise ValidationError("end_day_offset must be >= 0")

        if end_time is not None and start_time is None:
            raise ValidationError("end_time requires start_time")

        if notify_minutes_before is not None and notify_minutes_before < 0:
            raise ValidationError("notify_minutes_before must be >= 0")

        if repeat is not None:
            freq = repeat.get("freq")
            if freq is not None and freq not in {f.value for f in RepeatFreq}:
                raise ValidationError("repeat.freq must be none|daily|weekly|monthly")

        ts = now or utc_now()
        ev = Event(
            id=event_id or uuid4(),
            title=cleaned,
            date=day,
            start_time=start_time,
            end_time=end_time,
            end_day_offset=end_day_offset,
            notify=bool(notify),
            notify_minutes_before=notify_minutes_before,
            repeat=repeat,
            created_at=ts,
            updated_at=ts,
        )
        ev._validate_time_order()  # noqa: SLF001
        return ev

    def touch(self, *, now: datetime | None = None) -> None:
        self.updated_at = now or utc_now()

    def add_note(self, text: str, *, now: datetime | None = None) -> EventNote:
        note = EventNote.create(text, now=now)
        self.notes.append(note)
        self.touch(now=now)
        return note

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "title": self.title,
            "date": self.date.isoformat(),
            "start_time": (
                self.start_time.isoformat(timespec="minutes") if self.start_time else None
            ),
            "end_time": self.end_time.isoformat(timespec="minutes") if self.end_time else None,
            "end_day_offset": self.end_day_offset,
            "notify": self.notify,
            "notify_minutes_before": self.notify_minutes_before,
            "repeat": self.repeat,
            "notes": [n.to_dict() for n in self.notes],
            "created_at": _format_dt_utc(self.created_at),
            "updated_at": _format_dt_utc(self.updated_at),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Event":
        try:
            start_time = _parse_time(data.get("start_time"))
            end_time = _parse_time(data.get("end_time"))
            ev = Event(
                id=UUID(data["id"]),
                title=str(data["title"]),
                date=date.fromisoformat(data["date"]),
                start_time=start_time,
                end_time=end_time,
                end_day_offset=int(data.get("end_day_offset", 0)),
                notify=bool(data.get("notify", False)),
                notify_minutes_before=(
                    int(data["notify_minutes_before"])
                    if data.get("notify_minutes_before") is not None
                    else None
                ),
                repeat=data.get("repeat"),
                notes=[EventNote.from_dict(n) for n in (data.get("notes") or [])],
                created_at=_parse_dt_utc(data["created_at"]),
                updated_at=_parse_dt_utc(data["updated_at"]),
            )
            ev._validate_all()  # noqa: SLF001
            return ev
        except ValidationError:
            raise
        except (KeyError, TypeError, ValueError) as e:
            raise ValidationError(f"Invalid Event: {e}") from e

    def _validate_all(self) -> None:
        if not (self.title or "").strip():
            raise ValidationError("Event title cannot be empty")
        if not isinstance(self.end_day_offset, int) or self.end_day_offset < 0:
            raise ValidationError("end_day_offset must be >= 0")
        if self.end_time is not None and self.start_time is None:
            raise ValidationError("end_time requires start_time")
        if self.notify_minutes_before is not None and self.notify_minutes_before < 0:
            raise ValidationError("notify_minutes_before must be >= 0")
        if self.repeat is not None:
            freq = self.repeat.get("freq")
            if freq is not None and freq not in {f.value for f in RepeatFreq}:
                raise ValidationError("repeat.freq must be none|daily|weekly|monthly")
        self._validate_time_order()

    def _validate_time_order(self) -> None:
        if self.start_time is None or self.end_time is None:
            return
        start_dt = datetime.combine(self.date, self.start_time)
        end_dt = datetime.combine(self.date, self.end_time) + timedelta(days=self.end_day_offset)
        if end_dt < start_dt:
            raise ValidationError("end_dt must be >= start_dt")


def _parse_time(raw: Any) -> time | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValidationError("time must be a string")
    s = raw.strip()
    try:
        # Accept HH:MM
        hour_s, minute_s = s.split(":", 1)
        return time(hour=int(hour_s), minute=int(minute_s))
    except (TypeError, ValueError) as e:
        raise ValidationError(f"Invalid time: {raw} ({e})") from e


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
