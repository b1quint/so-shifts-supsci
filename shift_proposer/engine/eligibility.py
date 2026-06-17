"""Hard eligibility rules — who *may* take a block before scoring ranks them.

Pure: no ``gspread``, no filesystem. Eligibility is the gate that scoring never
overrides; a person who fails any rule here is removed from contention, and if
that empties the candidate pool the block is flagged unfilled (never
force-filled).

Two per-person hard rules (per CLAUDE.md):

* **No hard block** — reject a person who carries an ``X`` on *any* day of the
  block. ``?`` is penalized in scoring, not here; ``A/AS/AR/-`` are available.
* **Minimum rest** — at least ``min_rest_rotations`` rotations (a rotation is
  ``shift_len`` days) between the person's last shift and this block's start.

The third rule named in the design — "skip filled blocks" — is satisfied
upstream: :func:`engine.blocks.enumerate_blocks` only emits unfilled blocks, so
eligibility only reasons about people.
"""

from __future__ import annotations

from shift_proposer.config import Settings
from shift_proposer.engine.tallies import Tallies
from shift_proposer.models import AvailabilityGrid, Block, Code, Person


def is_available_for_block(grid: AvailabilityGrid, person: Person, block: Block) -> bool:
    """True unless ``person`` carries a hard ``X`` on any day of ``block``."""
    return all(grid.code(person, day) is not Code.X for day in block.dates)


def is_rested_for_block(
    tallies: Tallies,
    settings: Settings,
    person: Person,
    block: Block,
) -> bool:
    """True if ``person`` has had at least the minimum rest before ``block``.

    Rest required is ``min_rest_rotations * shift_len`` days between the person's
    last assigned shift and the block's start. A person with no prior shift is
    always rested.
    """
    gap = tallies.days_since_last_shift(person, block.start)
    if gap is None:
        return True
    return gap >= settings.min_rest_rotations * settings.shift_len


def is_eligible(
    grid: AvailabilityGrid,
    tallies: Tallies,
    settings: Settings,
    person: Person,
    block: Block,
) -> bool:
    """True if ``person`` passes every hard rule for ``block``."""
    return is_available_for_block(grid, person, block) and is_rested_for_block(
        tallies, settings, person, block
    )


def eligible_people(
    grid: AvailabilityGrid,
    tallies: Tallies,
    settings: Settings,
    block: Block,
) -> list[Person]:
    """All people eligible for ``block``, in :class:`AvailabilityGrid` order.

    Order is stable (grid order) so downstream tie-breaking is deterministic.
    """
    return [person for person in grid.people if is_eligible(grid, tallies, settings, person, block)]
