"""Render the per-person shift-utilization report (:mod:`engine.report`).

Pure: no ``gspread``, no filesystem beyond the explicit CSV write. Two views:

* :func:`render_report` — an aligned plain-text table for the terminal.
* :func:`write_report_csv` — the same rows as CSV for spreadsheet import.

Column shaping lives here so :mod:`engine.report` stays a pure value producer.
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from shift_proposer.engine.report import ShiftReportRow

_CSV_HEADER = (
    "person",
    "target_fte",
    "shift_days",
    "weekend_days",
    "shift_hours",
    "working_hours",
    "shift_fraction",
)


def _fte_seg(value: float | str | None, *, show: bool) -> str:
    """A ``"   NN%"`` table segment for the FTE column (empty when not shown).

    ``value`` is a header label (``str``), a fraction (``float``), or ``None``
    (no FTE entry → a dash). Width matches the ``"FTE"`` header so columns align.
    """
    if not show:
        return ""
    if isinstance(value, str):
        return f"  {value:>5}"
    if value is None:
        return f"  {'-':>5}"
    return f"  {value * 100:>4.0f}%"


def render_report(rows: Sequence[ShiftReportRow], *, start: date, end: date) -> str:
    """An aligned text table of ``rows`` plus a totals footer.

    The ``shift_fraction`` is shown as a percentage (1 dp); hours to whole
    numbers. A target-FTE column appears only when at least one row carries an
    FTE (i.e. an FTE tab was supplied). Totals sum shift/weekend days and
    shift-hours; the fraction footer is the pooled total (all shift-hours over
    one person's full-time hours).
    """
    header = f"Shift utilization — {start.isoformat()} → {end.isoformat()}"
    if not rows:
        return f"{header}\n(no assigned shifts in window)"

    show_fte = any(r.fte is not None for r in rows)
    name_w = max(len("Person"), max(len(r.person) for r in rows))
    cols = (
        f"{'Person':<{name_w}}{_fte_seg('FTE', show=show_fte)}  "
        f"{'Shifts':>6}  {'Weekend':>7}  {'Shift h':>8}  {'Frac':>7}"
    )
    lines = [header, cols, "-" * len(cols)]
    for r in rows:
        lines.append(
            f"{r.person:<{name_w}}{_fte_seg(r.fte, show=show_fte)}  "
            f"{r.shift_days:>6}  {r.weekend_days:>7}  "
            f"{r.shift_hours:>8.0f}  {r.shift_fraction * 100:>6.1f}%"
        )

    total_days = sum(r.shift_days for r in rows)
    total_weekend = sum(r.weekend_days for r in rows)
    total_hours = sum(r.shift_hours for r in rows)
    # Every row shares the same full-time denominator, so reuse the first.
    pooled = total_hours / rows[0].working_hours if rows[0].working_hours else 0.0
    lines.append("-" * len(cols))
    lines.append(
        f"{'TOTAL':<{name_w}}{_fte_seg('', show=show_fte)}  "
        f"{total_days:>6}  {total_weekend:>7}  "
        f"{total_hours:>8.0f}  {pooled * 100:>6.1f}%"
    )
    return "\n".join(lines)


def to_csv_rows(rows: Sequence[ShiftReportRow]) -> list[list[str]]:
    """The report as string rows, header first (pure — unit-testable).

    ``target_fte`` is written as a 0-1 fraction (blank when no FTE was supplied).
    """
    out: list[list[str]] = [list(_CSV_HEADER)]
    for r in rows:
        out.append(
            [
                r.person,
                "" if r.fte is None else f"{r.fte:.4f}",
                str(r.shift_days),
                str(r.weekend_days),
                f"{r.shift_hours:.1f}",
                f"{r.working_hours:.1f}",
                f"{r.shift_fraction:.4f}",
            ]
        )
    return out


def write_report_csv(rows: Sequence[ShiftReportRow], path: str | Path) -> Path:
    """Write the report rows to a CSV at ``path``; return the path written."""
    target = Path(path)
    with target.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(to_csv_rows(rows))
    return target
