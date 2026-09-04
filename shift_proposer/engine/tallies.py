"""Fairness counters — the heart of the scoring inputs.

Pure: no ``gspread``, no filesystem. The engine builds a :class:`Tallies`,
seeds it with the assignments already on the sheet, then mutates it as each
greedy pick is made. Scoring reads the *deficit* (how far below fair share a
person is) off this object.

Horizon: **YTD** shift-days within the relevant calendar year. (Weekend-day
fairness and its calendar-quarter horizon were dropped with the move to 7-day
Monday-anchored shifts — every shift now contains exactly one weekend, so
weekend load already tracks total-shift load and needs no separate term.)

Counting unit is **shift-days** (a 7-day block = 7 shift-days). Fair share is
**FTE-weighted**: every person carries a target FTE fraction (1.0 = full
dedication, 0.5 = half), and their target is ``total * fte_person / sum(fte)``
rather than a flat ``total / n_people``. A *deficit* is ``target - person_count``
so a positive value means "below fair share → boost". With equal FTE weights this
reduces exactly to the old equal split (``total / n_people``), so the default —
no FTE supplied → every person weight ``1.0`` — preserves prior behaviour.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date

from shift_proposer.config import Settings
from shift_proposer.models import Block, Person


@dataclass
class Tallies:
    """Mutable per-person counters over the run.

    Stores the raw set of assigned dates per person and derives YTD counts by
    filtering on year (double-recording a date is harmless).

    ``_fte`` holds each person's target FTE weight (fair share is proportional
    to it). Any person without an entry defaults to ``1.0``, so omitting the map
    entirely reproduces the old equal-split fair share.
    """

    people: tuple[Person, ...]
    settings: Settings
    _assigned: dict[Person, set[date]] = field(default_factory=dict)
    _fte: dict[Person, float] = field(default_factory=dict)

    @classmethod
    def empty(
        cls,
        people: Iterable[Person],
        settings: Settings,
        fte: Mapping[Person, float] | None = None,
    ) -> Tallies:
        """Build empty counters; ``fte`` maps a person to their target weight.

        A person missing from ``fte`` (or an omitted map) defaults to weight
        ``1.0``; extra keys not in ``people`` are ignored. Non-positive weights
        are rejected — a zero/negative FTE has no meaningful fair share.
        """
        people = tuple(people)
        weights = {p: float(fte[p]) for p in people if fte and p in fte}
        bad = {p.name: w for p, w in weights.items() if w <= 0}
        if bad:
            raise ValueError(f"FTE weights must be positive; got {bad}")
        return cls(
            people=people,
            settings=settings,
            _assigned={p: set() for p in people},
            _fte=weights,
        )

    def _weight(self, person: Person) -> float:
        """``person``'s FTE weight (default ``1.0`` when unspecified)."""
        return self._fte.get(person, 1.0)

    def _fair_target(self, counts: Mapping[Person, float], person: Person) -> float:
        """``person``'s FTE-weighted share of the total of ``counts``.

        ``total * weight_person / sum(weights)``. With equal weights this is the
        plain mean (``total / n_people``).
        """
        total = sum(counts.values())
        total_weight = sum(self._weight(p) for p in self.people)
        if total_weight == 0:
            return 0.0
        return total * self._weight(person) / total_weight

    # --- recording ---------------------------------------------------------

    def record_days(self, person: Person, days: Iterable[date]) -> None:
        """Add ``days`` to ``person``'s assigned set (idempotent per date)."""
        self._assigned.setdefault(person, set()).update(days)

    def record_block(self, person: Person, block: Block) -> None:
        """Record every day of ``block`` for ``person``."""
        self.record_days(person, block.dates)

    # --- raw counters ------------------------------------------------------

    def _days(self, person: Person) -> set[date]:
        return self._assigned.get(person, set())

    def shift_days(self, person: Person, year: int) -> int:
        """Total assigned shift-days for ``person`` in calendar ``year`` (YTD)."""
        return sum(1 for d in self._days(person) if d.year == year)

    def last_shift(self, person: Person) -> date | None:
        """The most recent assigned date for ``person`` (None if never assigned)."""
        days = self._days(person)
        return max(days) if days else None

    def days_since_last_shift(self, person: Person, as_of: date) -> int | None:
        """Days between ``person``'s last shift and ``as_of`` (None if none yet)."""
        last = self.last_shift(person)
        if last is None:
            return None
        return (as_of - last).days

    # --- fair-share deficits ----------------------------------------------

    def total_deficit(self, person: Person, as_of: date) -> float:
        """How far below the FTE-weighted fair share of total shift-days (YTD).

        Positive → below fair share (deserves a boost); negative → over.
        Computed for the calendar year of ``as_of``. Deficits still sum to zero
        across people (targets sum to the total), regardless of the weights.
        """
        year = as_of.year
        counts = {p: self.shift_days(p, year) for p in self.people}
        return self._fair_target(counts, person) - counts[person]
