"""Utilidades de formateo de fechas para la UI.

Nota: aquí centralizamos el formateo para evitar duplicar mapas de meses/días.
"""

from __future__ import annotations

from datetime import date, datetime

_EN_MONTHS_SHORT: dict[int, str] = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dec",
}

_EN_WEEKDAYS_SHORT: dict[int, str] = {
    0: "Mon",
    1: "Tue",
    2: "Wed",
    3: "Thu",
    4: "Fri",
    5: "Sat",
    6: "Sun",
}

_ES_WEEKDAYS_SHORT: dict[int, str] = {
    0: "Lun",
    1: "Mar",
    2: "Mié",
    3: "Jue",
    4: "Vie",
    5: "Sáb",
    6: "Dom",
}

_ES_MONTHS_SHORT: dict[int, str] = {
    1: "Ene",
    2: "Feb",
    3: "Mar",
    4: "Abr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Ago",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dic",
}


def fmt_day_full_friendly(day: date) -> str:
    """Formato fijo con año: `29 Dec, 2026`."""
    return f"{day.day} {_EN_MONTHS_SHORT.get(day.month, str(day.month))}, {day.year}"


def fmt_day_short_friendly(day: date, *, today: date) -> str:
    """Formato corto (manteniendo el comportamiento actual): `29 Dec, 2026`."""
    base = f"{day.day} {_EN_MONTHS_SHORT.get(day.month, str(day.month))}"
    return f"{base}, {day.year}"


def fmt_day_compact_friendly(day: date, *, today: date) -> str:
    """Formato compacto: `29 Dec` (sin año si es el año actual).

    Si el año es posterior al de `today`, incluye el año (mantiene el output actual de Events).
    """
    base = f"{day.day} {_EN_MONTHS_SHORT.get(day.month, str(day.month))}"
    if day.year > today.year:
        return f"{base}, {day.year}"
    return base


def fmt_header_date_es(dt: datetime) -> str:
    """Fecha para cabecera (es): `Mié 7 Ene 2026`."""
    wd = _ES_WEEKDAYS_SHORT.get(dt.weekday(), str(dt.weekday()))
    mo = _ES_MONTHS_SHORT.get(dt.month, str(dt.month))
    return f"{wd} {dt.day} {mo} {dt.year}"


def fmt_day_header_en(day: date) -> str:
    """Cabecera en inglés: `Mon 29 Dec, 2026` (usado por Journal)."""
    wd = _EN_WEEKDAYS_SHORT.get(day.weekday(), str(day.weekday()))
    mon = _EN_MONTHS_SHORT.get(day.month, str(day.month))
    return f"{wd} {day.day} {mon}, {day.year}"


def fmt_day_list_short_en(day: date) -> str:
    """Lista corta en inglés: `29 Dec 2026` (usado por Journal)."""
    mon = _EN_MONTHS_SHORT.get(day.month, str(day.month))
    return f"{day.day} {mon} {day.year}"
