"""Helpers de períodos: día / semana / mes con comparativos same-days-into.

Convención:
- Día: hoy (Bogotá) vs ayer
- Semana: lunes→hoy vs lunes-prev→domingo-prev (o lunes-prev → mismo nro de días)
- Mes: 1ro→hoy vs 1ro-prev → mismo día del mes (same-days-into)

Las funciones devuelven rangos [start, end] inclusive, en `date`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone


def bogota_today() -> date:
    return (datetime.now(timezone.utc) - timedelta(hours=5)).date()


@dataclass
class Period:
    label: str           # "day" | "week" | "month"
    current_start: date
    current_end: date    # inclusive
    prev_start: date
    prev_end: date       # inclusive (same number of days as current)
    granularity_label: str  # texto humano: "Hoy vs Ayer", "Semana en curso vs anterior", etc.


def periods_today(today: date | None = None) -> dict[str, Period]:
    today = today or bogota_today()

    # Día: hoy vs ayer
    day = Period(
        label="day",
        current_start=today,
        current_end=today,
        prev_start=today - timedelta(days=1),
        prev_end=today - timedelta(days=1),
        granularity_label="Hoy vs ayer",
    )

    # Semana: lunes hasta hoy vs lunes anterior hasta mismo día de la semana
    week_start = today - timedelta(days=today.weekday())  # lunes esta semana
    days_into = (today - week_start).days  # 0=lunes, 6=domingo
    prev_week_start = week_start - timedelta(days=7)
    prev_week_match_end = prev_week_start + timedelta(days=days_into)
    week = Period(
        label="week",
        current_start=week_start,
        current_end=today,
        prev_start=prev_week_start,
        prev_end=prev_week_match_end,
        granularity_label=f"Semana en curso ({days_into+1}d) vs misma porción semana pasada",
    )

    # Mes: primer día hasta hoy vs primer día mes pasado hasta mismo nro de día
    month_start = today.replace(day=1)
    days_into_m = (today - month_start).days
    if month_start.month == 1:
        prev_month_start = month_start.replace(year=month_start.year - 1, month=12, day=1)
    else:
        prev_month_start = month_start.replace(month=month_start.month - 1, day=1)
    prev_month_match_end = prev_month_start + timedelta(days=days_into_m)
    month = Period(
        label="month",
        current_start=month_start,
        current_end=today,
        prev_start=prev_month_start,
        prev_end=prev_month_match_end,
        granularity_label=f"MTD ({days_into_m+1}d) vs mismos días mes anterior",
    )

    return {"day": day, "week": week, "month": month}


def last_n_days(n: int, today: date | None = None) -> list[tuple[date, date]]:
    """Lista de N días terminando en today, ordenado de más viejo a más reciente."""
    today = today or bogota_today()
    return [(today - timedelta(days=i), today - timedelta(days=i)) for i in range(n - 1, -1, -1)]


def last_n_weeks(n: int, today: date | None = None) -> list[tuple[date, date, str]]:
    """Lista de N semanas terminando en la semana actual.

    Cada entry: (lunes, domingo, label "YYYY-MM-DD" del lunes).
    La última semana puede ser parcial (hasta hoy).
    """
    today = today or bogota_today()
    week_start = today - timedelta(days=today.weekday())
    out = []
    for i in range(n - 1, -1, -1):
        ws = week_start - timedelta(days=7 * i)
        we = ws + timedelta(days=6)
        # No proyectamos al futuro
        if we > today:
            we = today
        out.append((ws, we, ws.isoformat()))
    return out


def last_n_months(n: int, today: date | None = None) -> list[tuple[date, date, str]]:
    """Lista de N meses terminando en el mes actual.

    Cada entry: (1ro del mes, último día del mes, label "YYYY-MM").
    El mes actual puede ser parcial (hasta hoy).
    """
    today = today or bogota_today()
    out = []
    # cursor en el primero del mes actual
    y, m = today.year, today.month
    cursors: list[tuple[int, int]] = []
    for _ in range(n):
        cursors.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    cursors.reverse()
    for (y, m) in cursors:
        ms = date(y, m, 1)
        # Último día del mes
        if m == 12:
            next_m = date(y + 1, 1, 1)
        else:
            next_m = date(y, m + 1, 1)
        me = next_m - timedelta(days=1)
        if me > today:
            me = today
        out.append((ms, me, f"{y:04d}-{m:02d}"))
    return out
