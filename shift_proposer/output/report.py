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
    "shift_days",
    "weekend_days",
    "shift_hours",
    "working_hours",
    "shift_fraction",
)


def render_report(rows: Sequence[ShiftReportRow], *, start: date, end: date) -> str:
    """An aligned text table of ``rows`` plus a totals footer.

    The ``shift_fraction`` is shown as a percentage (1 dp); hours to whole
    numbers. Totals sum shift/weekend days and shift-hours; the fraction footer
    is the pooled total (all shift-hours over one person's full-time hours).
    """
    header = f"Shift utilization — {start.isoformat()} → {end.isoformat()}"
    if not rows:
        return f"{header}\n(no assigned shifts in window)"

    name_w = max(len("Person"), max(len(r.person) for r in rows))
    cols = f"{'Person':<{name_w}}  {'Shifts':>6}  {'Weekend':>7}  {'Shift h':>8}  {'Frac':>7}"
    lines = [header, cols, "-" * len(cols)]
    for r in rows:
        lines.append(
            f"{r.person:<{name_w}}  {r.shift_days:>6}  {r.weekend_days:>7}  "
            f"{r.shift_hours:>8.0f}  {r.shift_fraction * 100:>6.1f}%"
        )

    total_days = sum(r.shift_days for r in rows)
    total_weekend = sum(r.weekend_days for r in rows)
    total_hours = sum(r.shift_hours for r in rows)
    # Every row shares the same full-time denominator, so reuse the first.
    pooled = total_hours / rows[0].working_hours if rows[0].working_hours else 0.0
    lines.append("-" * len(cols))
    lines.append(
        f"{'TOTAL':<{name_w}}  {total_days:>6}  {total_weekend:>7}  "
        f"{total_hours:>8.0f}  {pooled * 100:>6.1f}%"
    )
    return "\n".join(lines)


def to_csv_rows(rows: Sequence[ShiftReportRow]) -> list[list[str]]:
    """The report as string rows, header first (pure — unit-testable)."""
    out: list[list[str]] = [list(_CSV_HEADER)]
    for r in rows:
        out.append(
            [
                r.person,
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
