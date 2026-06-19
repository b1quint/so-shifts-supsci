"""Per-person shift-utilization report — pure, read-only over existing shifts.

Unlike the proposer, this assigns nothing: it *summarises* the shifts already on
the sheet for debugging / investigation. For each person, within a date window,
it reports:

* ``shift_days``     — assigned dates falling inside the window
* ``weekend_days``   — those dates on a Saturday or Sunday
* ``shift_hours``    — ``shift_days × Settings.hours_per_shift`` (12 h/shift)
* ``working_hours``  — ``weeks_in_window × Settings.fulltime_hours_per_week``
* ``shift_fraction`` — ``shift_hours / working_hours``

The denominator is full-time (40 h/week) for everyone regardless of their FTE —
the same ``shift-hours / (weeks × 40 h)`` method the live ``Stats - SupSci`` tab
uses for its ``Used Fraction of Time``. So a person who is at half their *target*
FTE simply shows a smaller fraction; the report does not normalise by target.

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

    Counts **every calendar day in the range**, both endpoints included (so a
    Mon-Sun window is 7 days = exactly 1.0 weeks), and divides by 7 with no
    rounding. This is one day more than the ``Stats - SupSci`` tab's
    ``end - start`` span, so this report's fraction sits a touch below the tab's
    ``Used Fraction of Time`` — intentional, since we count every day worked.
    Raises ``ValueError`` if ``end`` precedes ``start``.
    """
    days = (end - start).days + 1
    if days <= 0:
        raise ValueError(f"window end {end} precedes start {start}")
    return days / 7.0


# Accepted values for build_report's ``sort_by`` (and the CLI ``--sort``).
SORT_SHEET = "sheet"  # preserve the spreadsheet's row order (default)
SORT_FTE = "fte"  # rank by target FTE, highest first
SORT_MODES = (SORT_SHEET, SORT_FTE)

# Target FTE assumed for a person absent from the FTE map when ranking — matches
# the engine's default weight (a missing entry is treated as full-time).
_DEFAULT_FTE = 1.0


@dataclass(frozen=True)
class ShiftReportRow:
    """One person's shift totals and utilization over the report window.

    ``fte`` is the person's target FTE fraction (0-1) when an FTE map was
    supplied, else ``None`` (not loaded — shown blank / omitted downstream).
    """

    person: str
    shift_days: int
    weekend_days: int
    shift_hours: float
    working_hours: float
    shift_fraction: float
    fte: float | None = None


def build_report(
    people: Iterable[Person],
    existing: Mapping[Person, Sequence[date]],
    *,
    start: date,
    end: date,
    settings: Settings,
    fte: Mapping[Person, float] | None = None,
    sort_by: str = SORT_SHEET,
) -> list[ShiftReportRow]:
    """Summarise each person's shifts in ``[start, end]`` (inclusive).

    ``existing`` is the parser's ``Person → assigned dates`` map. Only dates
    inside the window are counted, so the same map can drive any window. The
    full-time working-hours denominator depends only on the window length, so it
    is shared across people. ``fte`` (optional) maps a person to their target FTE
    fraction; when given it is recorded on each row.

    Ordering (``sort_by``):

    * ``"sheet"`` (default) — preserve the order of ``people`` (the spreadsheet
      row order, as the parser yields them).
    * ``"fte"`` — rank by target FTE, highest first; ties keep spreadsheet order
      (stable sort). A person with no FTE entry is treated as full-time (1.0).

    The result is deterministic for the same inputs. Raises ``ValueError`` for an
    unknown ``sort_by``.
    """
    if sort_by not in SORT_MODES:
        raise ValueError(f"unknown sort_by {sort_by!r} (expected one of {SORT_MODES})")

    weeks = window_weeks(start, end)
    working_hours = weeks * settings.fulltime_hours_per_week
    fte = fte or {}

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
                fte=fte.get(person),
            )
        )

    if sort_by == SORT_FTE:
        # Stable sort by FTE descending keeps spreadsheet order within ties.
        rows.sort(key=lambda r: -(r.fte if r.fte is not None else _DEFAULT_FTE))
    return rows
