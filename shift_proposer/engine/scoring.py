"""Score eligible candidates for a block — the soft ranking after the hard gate.

Pure: no ``gspread``, no filesystem. Eligibility (``engine.eligibility``) decides
*who may* take a block; scoring decides *who should*. Only call :func:`score` on
people that already passed the hard gate.

The score is a weighted sum (weights live in :class:`config.Settings`):

* ``+ w_total   * total_deficit``    — how far below fair share of total
  shift-days the person is (YTD). Below share → boost.
* ``+ w_spacing * days_since_last``   — reward rest; a longer gap scores higher.
* ``- w_question * n_question_days``  — penalty per ``?`` day in this block.
* ``- w_prep * n_unprepared_days``   — penalty per unavailable day (``X``) in the
  pre-shift prep window (the Wed/Thu/Fri immediately before the block starts).
  Not a hard block — a person can still take the shift — just a soft nudge
  towards someone who can actually prepare.

Higher is better. Every call returns a :class:`Rationale` whose ``terms`` are the
*weighted* contributions (they sum to the total), so a reviewer sees exactly what
drove each pick.
"""

from __future__ import annotations

from datetime import timedelta

from shift_proposer.config import Settings
from shift_proposer.engine.tallies import Tallies
from shift_proposer.models import AvailabilityGrid, Block, Code, Person, Rationale

# Offsets (in days, before block.start) of the prep-window Wed/Thu/Fri. A
# Monday-anchored block start minus 5/4/3 days lands on the prior Wed/Thu/Fri.
PREP_WINDOW_OFFSETS = (5, 4, 3)


def score(
    grid: AvailabilityGrid,
    tallies: Tallies,
    settings: Settings,
    person: Person,
    block: Block,
) -> tuple[float, Rationale]:
    """Score ``person`` for ``block``; return ``(total, Rationale)``.

    Measured as of the block's start. A person with no prior shift contributes
    ``0`` to the spacing term (their lead comes from the fair-share deficits, not
    an arbitrary "infinite rest" bonus); this is a deliberate, tunable choice.
    """
    as_of = block.start

    total_term = settings.w_total * tallies.total_deficit(person, as_of)

    gap = tallies.days_since_last_shift(person, as_of)
    spacing_term = settings.w_spacing * (gap if gap is not None else 0)

    n_question = sum(1 for day in block.dates if grid.code(person, day) is Code.QUESTION)
    question_term = -settings.w_question * n_question

    prepared_codes = settings.available_codes | {Code.QUESTION}
    prep_days = (as_of - timedelta(days=offset) for offset in PREP_WINDOW_OFFSETS)
    n_unprepared = sum(1 for day in prep_days if grid.code(person, day) not in prepared_codes)
    prep_term = -settings.w_prep * n_unprepared

    total = total_term + spacing_term + question_term + prep_term
    rationale = Rationale(
        total=total,
        terms={
            "total": total_term,
            "spacing": spacing_term,
            "question": question_term,
            "prep": prep_term,
        },
    )
    return total, rationale
