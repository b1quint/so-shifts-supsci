"""Render a :class:`Proposal` for human review.

Pure: no ``gspread``, no filesystem. This is the *representation* layer — it
turns the engine's output into something a reviewer reads and into structured
rows that :mod:`output.writeback` can persist (CSV / proposed column). Persisting
is writeback's job; shaping is here.

Two views, both chronological (assignments and flagged-unfilled blocks merged in
date order so the calendar reads top to bottom):

* :func:`to_rows` — a list of :class:`ProposalRow`, one per block, for tabular
  output. Each carries the per-term score breakdown so the *why* survives export.
* :func:`render_report` — a plain-text review report, one line per block with the
  score trace inline; unfilled blocks are flagged.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date

from shift_proposer.models import Proposal

# Preferred left-to-right order for the score terms; any unknown term sorts
# after these, alphabetically. Keeps reports and CSV columns stable.
_TERM_ORDER = ("total", "weekend", "spacing", "question")

STATUS_PROPOSED = "proposed"
STATUS_UNFILLED = "unfilled"


@dataclass(frozen=True)
class ProposalRow:
    """One block's worth of the proposal, flattened for tabular output.

    ``person``/``score``/``terms`` are empty for an unfilled block.
    """

    status: str
    start: date
    end: date
    person: str = ""
    score: float | None = None
    terms: Mapping[str, float] = field(default_factory=dict)


def _ordered_terms(terms: Mapping[str, float]) -> list[tuple[str, float]]:
    """Term ``(key, value)`` pairs in the stable preferred order."""
    known = [(k, terms[k]) for k in _TERM_ORDER if k in terms]
    extra = sorted((k, v) for k, v in terms.items() if k not in _TERM_ORDER)
    return known + extra


def term_columns(rows: Iterable[ProposalRow]) -> list[str]:
    """The union of term keys across ``rows``, in the stable preferred order.

    Used to build a consistent set of score-term columns for tabular export.
    """
    keys = {key for row in rows for key in row.terms}
    known = [k for k in _TERM_ORDER if k in keys]
    extra = sorted(k for k in keys if k not in _TERM_ORDER)
    return known + extra


def to_rows(proposal: Proposal) -> list[ProposalRow]:
    """Flatten ``proposal`` into chronological :class:`ProposalRow` records."""
    rows: list[ProposalRow] = []
    for assignment in proposal.assignments:
        block = assignment.block
        rows.append(
            ProposalRow(
                status=STATUS_PROPOSED,
                start=block.start,
                end=block.end,
                person=assignment.person.name,
                score=assignment.rationale.total,
                terms=dict(assignment.rationale.terms),
            )
        )
    for block in proposal.unfilled:
        rows.append(ProposalRow(status=STATUS_UNFILLED, start=block.start, end=block.end))
    rows.sort(key=lambda r: r.start)
    return rows


def _format_terms(terms: Mapping[str, float]) -> str:
    return " ".join(f"{k}={v:+.2f}" for k, v in _ordered_terms(terms))


def render_report(proposal: Proposal) -> str:
    """A plain-text review report: a header line then one line per block."""
    rows = to_rows(proposal)
    n_filled = sum(1 for r in rows if r.status == STATUS_PROPOSED)
    n_unfilled = len(rows) - n_filled

    lines = [f"Proposed shift calendar — {n_filled} assigned, {n_unfilled} unfilled"]
    for row in rows:
        span = f"{row.start.isoformat()} → {row.end.isoformat()}"
        if row.status == STATUS_UNFILLED:
            lines.append(f"{span}  ⚠ UNFILLED — no eligible candidate")
        else:
            trace = _format_terms(row.terms)
            lines.append(f"{span}  {row.person}  score={row.score:+.2f}  [{trace}]")
    return "\n".join(lines)
