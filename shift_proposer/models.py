"""Pure domain types for the shift proposer.

This module is part of the pure core: it imports nothing from ``gspread`` or
the filesystem. Everything here is a plain, immutable value object so the
scheduling logic stays portable (e.g. to the future Django backend) and
trivially unit-testable.

Policy (which codes count as "available", weights, rest length, ...) lives in
``config.Settings``, NOT here. These types only model the data.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Code(Enum):
    """Availability code as written in the SupSci tab (row 1 per date).

    Classification (available / penalized / blocking) is policy and lives in
    :class:`config.Settings`; this enum only models the raw values plus a
    parser from sheet text.
    """

    A = "A"  # available
    AS = "AS"  # available, summit
    AR = "AR"  # available, remote
    X = "X"  # unavailable — hard block
    QUESTION = "?"  # available but penalized
    DASH = "-"  # unanswered — assumed available

    @classmethod
    def parse(cls, raw: str | None) -> Code:
        """Parse a raw cell value into a :class:`Code`.

        Blank / unrecognized cells collapse to :attr:`DASH` (assumed
        available), matching the v1 decision that an unanswered date is
        treated as available.
        """
        if raw is None:
            return cls.DASH
        token = raw.strip().upper()
        if token == "":
            return cls.DASH
        if token == "?":
            return cls.QUESTION
        try:
            return cls(token)
        except ValueError:
            return cls.DASH


@dataclass(frozen=True)
class Person:
    """A scientist who can be assigned shifts.

    ``name`` is the stable identity used for dict keys and tie-breaking, so
    this type is frozen (hashable). The mapping back to spreadsheet rows for
    write-back is handled at the I/O boundary, not here.
    """

    name: str


@dataclass(frozen=True)
class AvailabilityGrid:
    """Availability codes indexed by ``(person, date)``.

    ``dates`` is the ordered window of columns from the sheet. Missing entries
    default to :attr:`Code.DASH` (assumed available) via :meth:`code`.
    """

    people: tuple[Person, ...]
    dates: tuple[date, ...]
    codes: Mapping[tuple[Person, date], Code]

    def code(self, person: Person, day: date) -> Code:
        """Return the code for ``person`` on ``day`` (DASH if unspecified)."""
        return self.codes.get((person, day), Code.DASH)


@dataclass(frozen=True)
class Block:
    """A contiguous run of dates to assign as a single shift.

    Blocks float freely (no weekday anchor) per the v1 decision; length is
    governed by ``Settings.shift_len`` when the block is enumerated.
    """

    dates: tuple[date, ...]

    @property
    def start(self) -> date:
        return self.dates[0]

    @property
    def end(self) -> date:
        return self.dates[-1]

    def weekend_days(self) -> tuple[date, ...]:
        """The Saturday/Sunday dates within this block."""
        return tuple(d for d in self.dates if d.weekday() >= 5)


@dataclass(frozen=True)
class Rationale:
    """Why a pick was made: the total score and its per-term breakdown.

    Every :class:`Assignment` carries one so a reviewer can see exactly why
    each candidate won.
    """

    total: float
    terms: Mapping[str, float]


@dataclass(frozen=True)
class Assignment:
    """A proposed assignment of one person to one block, with its rationale."""

    person: Person
    block: Block
    rationale: Rationale


@dataclass(frozen=True)
class Proposal:
    """The output of the engine.

    ``assignments`` are the proposed picks in date order; ``unfilled`` are
    blocks that had no eligible candidate (flagged, never force-filled).
    """

    assignments: tuple[Assignment, ...] = field(default_factory=tuple)
    unfilled: tuple[Block, ...] = field(default_factory=tuple)
