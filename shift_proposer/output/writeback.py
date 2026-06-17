"""Persist a :class:`Proposal` — for review, never into the live rows.

Two targets, both safe (neither touches the live ``SupSci`` assignment rows):

* a **CSV** — the full review table (status, span, person, score + term columns).
* the **in-sheet calendar** — the proposed picks placed into a SupSci-shaped
  *duplicate* tab the same way a human fills the original: a token in each
  assigned person's shift row, under each date, filling only empty cells.

CSV row shaping is reused from :mod:`output.proposal`. The calendar planner
(:func:`plan_calendar_fill`) is pure — it decides *which* cells to fill given
resolved row/date positions, leaving the gspread apply to :mod:`io.sheets`.
"""

from __future__ import annotations

import csv
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from shift_proposer.models import Proposal
from shift_proposer.output.proposal import term_columns, to_rows

_BASE_HEADER = ("status", "start", "end", "person", "score")


@dataclass(frozen=True)
class CellUpdate:
    """One cell to write: 0-indexed ``row``/``col`` and the string ``value``."""

    row: int
    col: int
    value: str


def plan_calendar_fill(
    proposal: Proposal,
    *,
    shift_row_by_name: Mapping[str, int],
    col_by_date: Mapping[date, int],
    is_empty: Callable[[int, int], bool],
    token: str = "S",
) -> list[CellUpdate]:
    """Plan the cells to fill for ``proposal`` in a SupSci-shaped tab.

    For each proposed assignment, writes ``token`` into that person's shift row
    (``shift_row_by_name``) under each date of the block (``col_by_date``) — but
    only where ``is_empty(row, col)`` holds, so existing assignments are never
    overwritten ("populate the missing values"). Unfilled blocks write nothing.

    A person or date with no mapped position is skipped (the caller can detect
    this by comparing the update count to the proposed shift-days).
    """
    updates: list[CellUpdate] = []
    for assignment in proposal.assignments:
        row = shift_row_by_name.get(assignment.person.name)
        if row is None:
            continue
        for day in assignment.block.dates:
            col = col_by_date.get(day)
            if col is None:
                continue
            if is_empty(row, col):
                updates.append(CellUpdate(row=row, col=col, value=token))
    return updates


def _num(value: float | None) -> str:
    """Format a numeric cell to 4 dp; blank for ``None`` (unfilled rows)."""
    return "" if value is None else f"{value:.4f}"


def to_csv_rows(proposal: Proposal) -> list[list[str]]:
    """The CSV as a list of string rows, header first.

    Pure (no filesystem) so the exact output is unit-testable. Score-term columns
    are appended after the base columns, in the stable preferred order.
    """
    rows = to_rows(proposal)
    terms = term_columns(rows)
    header = [*_BASE_HEADER, *terms]

    out: list[list[str]] = [header]
    for row in rows:
        out.append(
            [
                row.status,
                row.start.isoformat(),
                row.end.isoformat(),
                row.person,
                _num(row.score),
                *(_num(row.terms.get(term)) for term in terms),
            ]
        )
    return out


def _write_rows(rows: Sequence[Sequence[str]], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)


def write_csv(proposal: Proposal, path: str | Path) -> Path:
    """Write ``proposal`` to a CSV at ``path``; return the path written."""
    target = Path(path)
    _write_rows(to_csv_rows(proposal), target)
    return target
