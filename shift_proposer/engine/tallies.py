"""Two-horizon fairness counters — the heart of the scoring inputs.

Pure: no ``gspread``, no filesystem. The engine builds a :class:`Tallies`,
seeds it with the assignments already on the sheet, then mutates it as each
greedy pick is made. Scoring reads the *deficits* (how far below fair share a
person is) off this object.

Two horizons (per CLAUDE.md):

* **YTD** — shift-days and weekend-days within the relevant calendar year.
* **Calendar quarter** — weekend-days within the current quarter, whose counter
  is *seeded* from the prior quarter (carry-over) rather than reset cold.

Counting unit is **shift-days** (a 4-day block = 4 shift-days). Fair share is an
**equal split**: every person's target is ``total / n_people``. A *deficit* is
``mean - person_count`` so a positive value means "below fair share → boost".

The quarter seed mode is policy (``Settings.quarter_seed``); the default
``carry_deviation`` carries each person's prior-quarter deviation-from-mean into
the new quarter. Swapping to ``carry_total`` / ``zero`` is a one-line change in
:meth:`Tallies._quarter_seed`.
"""

from __future__ import annotations

from collections.abc import Iterable
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


def _mean(values: Iterable[float]) -> float:
    vals = list(values)
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


@dataclass
class Tallies:
    """Mutable per-person counters over the run.

    Stores the raw set of assigned dates per person and derives every horizon
    by filtering, so YTD vs. quarter are just different views of one source of
    truth (and double-recording a date is harmless).
    """

    people: tuple[Person, ...]
    settings: Settings
    _assigned: dict[Person, set[date]] = field(default_factory=dict)

    @classmethod
    def empty(cls, people: Iterable[Person], settings: Settings) -> Tallies:
        people = tuple(people)
        return cls(people=people, settings=settings, _assigned={p: set() for p in people})

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
        """How far below the equal-split fair share of total shift-days (YTD).

        Positive → below fair share (deserves a boost); negative → over.
        Computed for the calendar year of ``as_of``.
        """
        year = as_of.year
        counts = {p: self.shift_days(p, year) for p in self.people}
        return _mean(counts.values()) - counts[person]

    def weekend_deficit(self, person: Person, as_of: date) -> float:
        """Weekend fair-share deficit combining the YTD and quarter horizons.

        ``ytd_term + quarter_term``, each an equal-split deficit (mean minus the
        person's count). The quarter term's counter is seeded from the prior
        quarter per ``Settings.quarter_seed``. Positive → below fair share.
        """
        year = as_of.year
        q = quarter_of(as_of)
        prior = previous_quarter(q)

        # YTD horizon
        ytd = {p: self.weekend_days(p, year) for p in self.people}
        ytd_term = _mean(ytd.values()) - ytd[person]

        # Calendar-quarter horizon, seeded from the prior quarter
        current = {
            p: self._quarter_seed(p, prior) + self.weekend_days_in_quarter(p, q)
            for p in self.people
        }
        quarter_term = _mean(current.values()) - current[person]

        return ytd_term + quarter_term

    def _quarter_seed(self, person: Person, prior: QuarterKey) -> float:
        """Starting weekend value for the current quarter (carry-over).

        One-line policy switch (``Settings.quarter_seed``):

        * ``carry_deviation`` (default) — prior-quarter deviation from the mean.
        * ``carry_total`` — the prior-quarter raw count.
        * ``zero`` — cold reset.
        """
        mode = self.settings.quarter_seed
        if mode == "zero":
            return 0.0
        prior_count = self.weekend_days_in_quarter(person, prior)
        if mode == "carry_total":
            return float(prior_count)
        # carry_deviation (default)
        mean_prior = _mean(self.weekend_days_in_quarter(p, prior) for p in self.people)
        return prior_count - mean_prior
