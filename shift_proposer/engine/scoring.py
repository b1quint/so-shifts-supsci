"""Score eligible candidates for a block — the soft ranking after the hard gate.

Pure: no ``gspread``, no filesystem. Eligibility (``engine.eligibility``) decides
*who may* take a block; scoring decides *who should*. Only call :func:`score` on
people that already passed the hard gate.

The score is a weighted sum (weights live in :class:`config.Settings`):

* ``+ w_total   * total_deficit``    — how far below fair share of total
  shift-days the person is (YTD). Below share → boost.
* ``+ w_weekend * weekend_deficit``  — same idea for weekend-days, combining the
  YTD and calendar-quarter horizons.
* ``+ w_spacing * days_since_last``   — reward rest; a longer gap scores higher.
* ``- w_question * n_question_days``  — penalty per ``?`` day in this block.

Higher is better. Every call returns a :class:`Rationale` whose ``terms`` are the
*weighted* contributions (they sum to the total), so a reviewer sees exactly what
drove each pick.
"""

from __future__ import annotations

from shift_proposer.config import Settings
from shift_proposer.engine.tallies import Tallies
from shift_proposer.models import AvailabilityGrid, Block, Code, Person, Rationale


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
    weekend_term = settings.w_weekend * tallies.weekend_deficit(person, as_of)

    gap = tallies.days_since_last_shift(person, as_of)
    spacing_term = settings.w_spacing * (gap if gap is not None else 0)

    n_question = sum(1 for day in block.dates if grid.code(person, day) is Code.QUESTION)
    question_term = -settings.w_question * n_question

    total = total_term + weekend_term + spacing_term + question_term
    rationale = Rationale(
        total=total,
        terms={
            "total": total_term,
            "weekend": weekend_term,
            "spacing": spacing_term,
            "question": question_term,
        },
    )
    return total, rationale
