"""Two-horizon fairness counters — the heart of the scoring inputs.

Pure: no ``gspread``, no filesystem. The engine builds a :class:`Tallies`,
seeds it with the assignments already on the sheet, then mutates it as each
greedy pick is made. Scoring reads the *deficits* (how far below fair share a
person is) off this object.

Two horizons (per CLAUDE.md):

* **YTD** — shift-days and weekend-days within the relevant calendar year.
* **Calendar quarter** — weekend-days within the current quarter, whose counter
  is *seeded* from the prior quarter (carry-over) rather than reset cold.

Counting unit is **shift-days** (a 4-day block = 4 shift-days). Fair share is
**FTE-weighted**: every person carries a target FTE fraction (1.0 = full
dedication, 0.5 = half), and their target is ``total * fte_person / sum(fte)``
rather than a flat ``total / n_people``. A *deficit* is ``target - person_count``
so a positive value means "below fair share → boost". With equal FTE weights this
reduces exactly to the old equal split (``total / n_people``), so the default —
no FTE supplied → every person weight ``1.0`` — preserves prior behaviour.

The quarter seed mode is policy (``Settings.quarter_seed``); the default
``carry_deviation`` carries each person's prior-quarter deviation-from-mean into
the new quarter. Swapping to ``carry_total`` / ``zero`` is a one-line change in
:meth:`Tallies._quarter_seed`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date

from shift_proposer.config import Settings
from shift_proposer.models import Block, Person

QuarterKey = tuple[int, int]  # (year, quarter 1-4)


def quarter_of(day: date) -> QuarterKey:
    """Calendar quarter containing ``day`` as ``(year, 1..4)``."""
    return (day.year, (day.month - 1) // 3 + 1)


def previous_quarter(q: QuarterKey) -> QuarterKey:
    """The quarter immediately before ``q`` (wraps across the year boundary)."""
    year, quarter = q
    if quarter == 1:
        return (year - 1, 4)
    return (year, quarter - 1)


def _is_weekend(day: date) -> bool:
    return day.weekday() >= 5  # Sat=5, Sun=6


@dataclass
class Tallies:
    """Mutable per-person counters over the run.

    Stores the raw set of assigned dates per person and derives every horizon
    by filtering, so YTD vs. quarter are just different views of one source of
    truth (and double-recording a date is harmless).

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

    def weekend_days(self, person: Person, year: int) -> int:
        """Assigned weekend (Sat/Sun) shift-days for ``person`` in ``year`` (YTD)."""
        return sum(1 for d in self._days(person) if d.year == year and _is_weekend(d))

    def weekend_days_in_quarter(self, person: Person, q: QuarterKey) -> int:
        """Assigned weekend shift-days for ``person`` within quarter ``q``."""
        return sum(1 for d in self._days(person) if _is_weekend(d) and quarter_of(d) == q)

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

    def weekend_deficit(self, person: Person, as_of: date) -> float:
        """Weekend fair-share deficit combining the YTD and quarter horizons.

        ``ytd_term + quarter_term``, each an FTE-weighted deficit (the person's
        weighted target minus their count). The quarter term's counter is seeded
        from the prior quarter per ``Settings.quarter_seed``. Positive → below
        fair share.
        """
        year = as_of.year
        q = quarter_of(as_of)
        prior = previous_quarter(q)

        # YTD horizon
        ytd = {p: self.weekend_days(p, year) for p in self.people}
        ytd_term = self._fair_target(ytd, person) - ytd[person]

        # Calendar-quarter horizon, seeded from the prior quarter
        current = {
            p: self._quarter_seed(p, prior) + self.weekend_days_in_quarter(p, q)
            for p in self.people
        }
        quarter_term = self._fair_target(current, person) - current[person]

        return ytd_term + quarter_term

    def _quarter_seed(self, person: Person, prior: QuarterKey) -> float:
        """Starting weekend value for the current quarter (carry-over).

        One-line policy switch (``Settings.quarter_seed``):

        * ``carry_deviation`` (default) — prior-quarter deviation from the
          person's FTE-weighted target.
        * ``carry_total`` — the prior-quarter raw count.
        * ``zero`` — cold reset.
        """
        mode = self.settings.quarter_seed
        if mode == "zero":
            return 0.0
        prior_count = self.weekend_days_in_quarter(person, prior)
        if mode == "carry_total":
            return float(prior_count)
        # carry_deviation (default): deviation from the FTE-weighted target.
        prior_counts = {p: self.weekend_days_in_quarter(p, prior) for p in self.people}
        return prior_count - self._fair_target(prior_counts, person)
