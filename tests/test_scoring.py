"""Step-3 tests for engine/scoring — the soft ranking of eligible candidates.

All pure: hand-built people, dates, an AvailabilityGrid, and a Tallies seeded
with prior shifts. We assert each weighted term in isolation, the '?' penalty,
the spacing handling for a never-assigned person, and that the rationale's terms
sum to the reported total.
"""

from dataclasses import replace
from datetime import date, timedelta

from shift_proposer.config import Settings
from shift_proposer.engine.scoring import score
from shift_proposer.engine.tallies import Tallies
from shift_proposer.models import AvailabilityGrid, Block, Code, Person

ANN = Person("Ann")
BO = Person("Bo")
CAI = Person("Cai")
PEOPLE = (ANN, BO, CAI)

MON = date(2026, 6, 1)
SETTINGS = Settings()


def days(start: date, n: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


def block(start: date, n: int = 4) -> Block:
    return Block(dates=tuple(days(start, n)))


def grid(codes: dict[tuple[Person, date], Code], dates: tuple[date, ...]) -> AvailabilityGrid:
    return AvailabilityGrid(people=PEOPLE, dates=dates, codes=codes)


def test_terms_sum_to_total():
    b = block(MON)
    t = Tallies.empty(PEOPLE, SETTINGS)
    total, rationale = score(grid({}, b.dates), t, SETTINGS, ANN, b)
    assert rationale.total == total
    assert sum(rationale.terms.values()) == total


def test_underloaded_person_outscores_overloaded_peer():
    # Bo already carries a block; Ann/Cai carry none. Ann should score higher.
    b = block(MON + timedelta(days=30))
    t = Tallies.empty(PEOPLE, SETTINGS)
    t.record_block(BO, block(MON))
    g = grid({}, b.dates)
    ann, _ = score(g, t, SETTINGS, ANN, b)
    bo, _ = score(g, t, SETTINGS, BO, b)
    assert ann > bo


def test_question_days_apply_a_penalty():
    b = block(MON)
    t = Tallies.empty(PEOPLE, SETTINGS)
    clean = grid({}, b.dates)
    penalized = grid({(ANN, b.dates[0]): Code.QUESTION, (ANN, b.dates[1]): Code.QUESTION}, b.dates)
    base, base_r = score(clean, t, SETTINGS, ANN, b)
    pen, pen_r = score(penalized, t, SETTINGS, ANN, b)
    assert pen_r.terms["question"] == -SETTINGS.w_question * 2
    assert pen == base - SETTINGS.w_question * 2


def test_spacing_rewards_a_longer_rest():
    t = Tallies.empty(PEOPLE, SETTINGS)
    t.record_days(ANN, [MON])
    near = block(MON + timedelta(days=10))
    far = block(MON + timedelta(days=40))
    near_score, _ = score(grid({}, near.dates), t, SETTINGS, ANN, near)
    far_score, _ = score(grid({}, far.dates), t, SETTINGS, ANN, far)
    assert far_score > near_score


def test_never_assigned_person_gets_zero_spacing_term():
    b = block(MON)
    t = Tallies.empty(PEOPLE, SETTINGS)
    _, rationale = score(grid({}, b.dates), t, SETTINGS, ANN, b)
    assert rationale.terms["spacing"] == 0.0


def test_weights_scale_their_terms():
    # Zero every weight but w_question: only the penalty term should remain.
    settings = replace(SETTINGS, w_total=0.0, w_weekend=0.0, w_spacing=0.0, w_question=1.0)
    b = block(MON)
    t = Tallies.empty(PEOPLE, settings)
    t.record_block(BO, block(MON - timedelta(days=60)))  # make deficits nonzero
    g = grid({(ANN, b.dates[0]): Code.QUESTION}, b.dates)
    total, rationale = score(g, t, settings, ANN, b)
    assert rationale.terms["total"] == 0.0
    assert rationale.terms["weekend"] == 0.0
    assert rationale.terms["spacing"] == 0.0
    assert total == -1.0
