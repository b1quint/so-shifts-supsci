"""Per-person shift-utilization report — pure, read-only over existing shifts.

Unlike the proposer, this assigns nothing: it *summarises* the shifts already on
the sheet for debugging / investigation. For each person, within a date window,
it reports:

* ``shift_days``     — assigned dates falling inside the window
* ``weekend_days``   — those dates on a Saturday or Sunday
* ``shift_hours``    — ``shift_days × Settings.hours_per_shift`` (12 h/shift)
* ``working_hours``  — ``weeks_in_window × Settings.fulltime_hours_per_week``
* ``shift_fraction`` — ``shift_hours / working_hours``

The denominator is full-time (40 h/week) for everyone regardless of their FTE,
matching the live ``Stats - SupSci`` tab's ``Used Fraction of Time``. So a person
who is at half their *target* FTE simply shows a smaller fraction; the report does
not normalise by target.

Pure: no ``gspread``, no filesystem — feed it the ``existing`` map the parser
returns and a window, get plain value objects back.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from shift_proposer.config import Settings
from shift_proposer.models import Person


def _is_weekend(day: date) -> bool:
    return day.weekday() >= 5  # Sat=5, Sun=6


def window_weeks(start: date, end: date) -> float:
    """Number of weeks spanned by the inclusive window ``[start, end]``.

    Counts whole days inclusively (so a Mon-Sun window is exactly 1.0 weeks) and
    divides by 7. Raises ``ValueError`` if ``end`` precedes ``start``.
    """
    days = (end - start).days + 1
    if days <= 0:
        raise ValueError(f"window end {end} precedes start {start}")
    return days / 7.0


@dataclass(frozen=True)
class ShiftReportRow:
    """One person's shift totals and utilization over the report window."""

    person: str
    shift_days: int
    weekend_days: int
    shift_hours: float
    working_hours: float
    shift_fraction: float


def build_report(
    people: Iterable[Person],
    existing: Mapping[Person, Sequence[date]],
    *,
    start: date,
    end: date,
    settings: Settings,
) -> list[ShiftReportRow]:
    """Summarise each person's shifts in ``[start, end]`` (inclusive).

    ``existing`` is the parser's ``Person → assigned dates`` map. Only dates
    inside the window are counted, so the same map can drive any window. The
    full-time working-hours denominator depends only on the window length, so it
    is shared across people. Rows are returned sorted by most shift-days first,
    then by name — deterministic for the same inputs.
    """
    weeks = window_weeks(start, end)
    working_hours = weeks * settings.fulltime_hours_per_week

    rows: list[ShiftReportRow] = []
    for person in people:
        in_window = [d for d in existing.get(person, ()) if start <= d <= end]
        n_days = len(in_window)
        n_weekend = sum(1 for d in in_window if _is_weekend(d))
        shift_hours = n_days * settings.hours_per_shift
        fraction = shift_hours / working_hours if working_hours else 0.0
        rows.append(
            ShiftReportRow(
                person=person.name,
                shift_days=n_days,
                weekend_days=n_weekend,
                shift_hours=shift_hours,
                working_hours=working_hours,
                shift_fraction=fraction,
            )
        )

    rows.sort(key=lambda r: (-r.shift_days, r.person))
    return rows
