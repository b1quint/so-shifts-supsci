"""The greedy fill — walk blocks in date order and make one pick each.

Pure: no ``gspread``, no filesystem. This is the engine's entrypoint. It seeds a
:class:`Tallies` from the assignments already on the sheet, enumerates the
unfilled blocks, and for each block in date order:

1. gather the eligible people (hard gate, ``engine.eligibility``),
2. score each (``engine.scoring``),
3. pick the highest score — stable tie-break: **lowest YTD shift-days, then
   name** — record it into the tallies so later blocks see the updated load, and
4. if no one is eligible, flag the block *unfilled* (never force-fill; the rest
   rule is never violated).

Greedy is chosen over an optimizer for v1: simple, explainable, tunable. Every
:class:`Assignment` carries its :class:`Rationale` so a reviewer sees why each
pick won. Determinism is guaranteed by the stable tie-break plus the date-ordered
blocks and grid-ordered candidate pool.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date

from shift_proposer.config import Settings
from shift_proposer.engine.blocks import enumerate_blocks
from shift_proposer.engine.eligibility import eligible_people
from shift_proposer.engine.scoring import score
from shift_proposer.engine.tallies import Tallies
from shift_proposer.models import (
    Assignment,
    AvailabilityGrid,
    Person,
    Proposal,
)


def propose(
    grid: AvailabilityGrid,
    settings: Settings,
    existing: Mapping[Person, Iterable[date]] | None = None,
) -> Proposal:
    """Build a :class:`Proposal` for ``grid`` under ``settings``.

    ``existing`` maps each person to the dates they are *already* assigned on the
    sheet; those dates seed the fairness tallies and are treated as filled, so no
    block is proposed over them. Returns the proposed assignments (date order)
    plus any blocks left unfilled for lack of an eligible candidate.
    """
    tallies = Tallies.empty(grid.people, settings)
    filled: set[date] = set()
    for person, dates in (existing or {}).items():
        seeded = tuple(dates)
        tallies.record_days(person, seeded)
        filled.update(seeded)

    blocks = enumerate_blocks(grid.dates, filled, settings.shift_len)

    assignments: list[Assignment] = []
    unfilled = []
    for block in blocks:
        candidates = eligible_people(grid, tallies, settings, block)
        if not candidates:
            unfilled.append(block)
            continue

        year = block.start.year
        scored = [(person, *score(grid, tallies, settings, person, block)) for person in candidates]
        # Highest score wins; ties broken by lowest YTD load, then name.
        best_person, _, best_rationale = min(
            scored,
            key=lambda s: (-s[1], tallies.shift_days(s[0], year), s[0].name),
        )

        tallies.record_block(best_person, block)
        assignments.append(Assignment(person=best_person, block=block, rationale=best_rationale))

    return Proposal(assignments=tuple(assignments), unfilled=tuple(unfilled))
