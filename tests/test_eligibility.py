"""Step-3 tests for engine/eligibility — the hard candidate gate.

All pure: hand-built people, dates, an AvailabilityGrid, and a Tallies seeded
with prior shifts. We assert the two per-person hard rules (no ``X`` anywhere in
the block; minimum rest since last shift) and that scoring-only codes (``?``)
stay eligible.
"""

from datetime import date, timedelta

from shift_proposer.config import Settings
from shift_proposer.engine.eligibility import (
    eligible_people,
    is_available_for_block,
    is_eligible,
    is_rested_for_block,
)
from shift_proposer.engine.tallies import Tallies
from shift_proposer.models import AvailabilityGrid, Block, Code, Person

ANN = Person("Ann")
BO = Person("Bo")
CAI = Person("Cai")
PEOPLE = (ANN, BO, CAI)

MON = date(2026, 6, 1)
SETTINGS = Settings()  # shift_len=4, min_rest_rotations=2 -> 8 days rest


def days(start: date, n: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


def block(start: date, n: int = 4) -> Block:
    return Block(dates=tuple(days(start, n)))


def grid(codes: dict[tuple[Person, date], Code], dates: tuple[date, ...]) -> AvailabilityGrid:
    return AvailabilityGrid(people=PEOPLE, dates=dates, codes=codes)


# --- availability (the 'X' rule) -------------------------------------------


def test_all_available_is_available():
    b = block(MON)
    g = grid({}, b.dates)  # empty -> all DASH (assumed available)
    assert is_available_for_block(g, ANN, b) is True


def test_single_x_anywhere_blocks_the_person():
    b = block(MON)
    g = grid({(ANN, b.dates[2]): Code.X}, b.dates)
    assert is_available_for_block(g, ANN, b) is False


def test_question_code_stays_available():
    b = block(MON)
    g = grid({(ANN, b.dates[0]): Code.QUESTION}, b.dates)
    # '?' is penalized in scoring, not a hard block.
    assert is_available_for_block(g, ANN, b) is True


def test_x_outside_the_block_does_not_block():
    b = block(MON)
    outside = b.dates[-1] + timedelta(days=10)
    g = grid({(ANN, outside): Code.X}, b.dates + (outside,))
    assert is_available_for_block(g, ANN, b) is True


# --- minimum rest ----------------------------------------------------------


def test_no_prior_shift_is_always_rested():
    t = Tallies.empty(PEOPLE, SETTINGS)
    assert is_rested_for_block(t, SETTINGS, ANN, block(MON)) is True


def test_rest_exactly_at_threshold_passes():
    t = Tallies.empty(PEOPLE, SETTINGS)
    t.record_days(ANN, [MON])  # last shift on MON
    # 8 days rest required; start exactly 8 days after the last shift.
    assert is_rested_for_block(t, SETTINGS, ANN, block(MON + timedelta(days=8))) is True


def test_rest_below_threshold_fails():
    t = Tallies.empty(PEOPLE, SETTINGS)
    t.record_days(ANN, [MON])
    assert is_rested_for_block(t, SETTINGS, ANN, block(MON + timedelta(days=7))) is False


# --- combined gate + pool ordering -----------------------------------------


def test_is_eligible_requires_both_rules():
    b = block(MON + timedelta(days=8))
    t = Tallies.empty(PEOPLE, SETTINGS)
    t.record_days(ANN, [MON])  # rested by exactly 8 days
    g = grid({(ANN, b.dates[0]): Code.X}, b.dates)
    # rested but hard-blocked -> ineligible
    assert is_eligible(g, t, SETTINGS, ANN, b) is False


def test_eligible_people_filters_and_preserves_grid_order():
    b = block(MON + timedelta(days=8))
    t = Tallies.empty(PEOPLE, SETTINGS)
    t.record_days(BO, [MON + timedelta(days=5)])  # Bo under-rested (3 days)
    g = grid({(CAI, b.dates[1]): Code.X}, b.dates)  # Cai hard-blocked
    # Ann: rested + available; Bo: under-rested; Cai: blocked.
    assert eligible_people(g, t, SETTINGS, b) == [ANN]


def test_empty_pool_when_no_one_eligible():
    b = block(MON)
    g = grid({(p, d): Code.X for p in PEOPLE for d in b.dates}, b.dates)
    t = Tallies.empty(PEOPLE, SETTINGS)
    assert eligible_people(g, t, SETTINGS, b) == []
