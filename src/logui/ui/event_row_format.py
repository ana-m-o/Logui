from __future__ import annotations

from collections.abc import Callable
from datetime import date

from logui.domain.entities.event import Event, EventNote


def format_event_notes_block(notes: list[EventNote]) -> str:
    lines: list[str] = []
    for note in notes:
        text = (note.text or "").strip()
        if not text:
            continue
        lines.append(f"- {text}")

    return "\n".join(lines)


def event_notify_glyph(ev: Event) -> str:
    return "🕭" if ev.notify else " "


def format_event_row(
    ev: Event,
    *,
    today: date,
    fmt_day_friendly: Callable[[date], str],
) -> str:
    start_day = ev.date
    end_day = start_day.fromordinal(start_day.toordinal() + int(ev.end_day_offset or 0))

    day_part = fmt_day_friendly(start_day)

    time_part = "All day"
    if ev.start_time is None:
        if ev.end_day_offset and ev.end_day_offset > 0:
            day_part = f"{day_part}–{fmt_day_friendly(end_day)}"
    else:
        start_s = ev.start_time.strftime("%H:%M")
        end_s = ev.end_time.strftime("%H:%M") if ev.end_time else "??"
        if ev.end_day_offset and ev.end_day_offset > 0:
            time_part = f"{start_s}–{fmt_day_friendly(end_day)} {end_s}"
        else:
            time_part = f"{start_s}–{end_s}"

    repeat_part = ""
    if ev.repeat and isinstance(ev.repeat, dict):
        freq = str(ev.repeat.get("freq") or "")
        if freq and freq != "none":
            repeat_part = f" ({freq})"

    return f"{day_part} {time_part}  {ev.title}{repeat_part}"
