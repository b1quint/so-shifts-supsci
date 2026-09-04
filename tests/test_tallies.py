"""Step-2 tests for engine/tallies — the YTD fair-share counters.

All pure: hand-built people + dates, no Sheets, no network. We assert basic
counting, last-shift tracking, and the FTE-weighted fair-share deficit.
"""

from datetime import date

import pytest

from shift_proposer.config import Settings
from shift_proposer.engine.tallies import Tallies
from shift_proposer.models import Block, Person

ANN = Person("Ann")
BO = Person("Bo")
CAI = Person("Cai")
PEOPLE = (ANN, BO, CAI)

SETTINGS = Settings()


def make() -> Tallies:
    return Tallies.empty(PEOPLE, SETTINGS)


# --- recording & basic counters -------------------------------------------


def test_empty_tallies_have_zero_counts_and_no_last_shift():
    t = make()
    asof = date(2026, 6, 16)
    assert t.shift_days(ANN, 2026) == 0
    assert t.last_shift(ANN) is None
    assert t.days_since_last_shift(ANN, asof) is None


def test_record_block_counts_shift_days_and_updates_last_shift():
    t = make()
    block = Block(
        dates=(date(2026, 6, 12), date(2026, 6, 13), date(2026, 6, 14), date(2026, 6, 15))
    )
    t.record_block(ANN, block)
    assert t.shift_days(ANN, 2026) == 4
    assert t.last_shift(ANN) == date(2026, 6, 15)


def test_record_is_idempotent_on_duplicate_days():
    t = make()
    days = (date(2026, 6, 13), date(2026, 6, 14))
    t.record_days(ANN, days)
    t.record_days(ANN, days)  # same days again — must not double-count
    assert t.shift_days(ANN, 2026) == 2


def test_days_since_last_shift_is_gap_in_days():
    t = make()
    t.record_days(ANN, (date(2026, 6, 10),))
    assert t.days_since_last_shift(ANN, date(2026, 6, 16)) == 6


def test_ytd_counts_only_the_given_year():
    t = make()
    t.record_days(ANN, (date(2025, 12, 20), date(2026, 1, 5)))
    assert t.shift_days(ANN, 2026) == 1
    assert t.shift_days(ANN, 2025) == 1


# --- fair-share deficits ---------------------------------------------------


def test_total_deficit_positive_when_below_average_and_sums_to_zero():
    t = make()
    asof = date(2026, 6, 16)
    # Ann 4 days, Bo 0, Cai 0 -> mean 4/3.
    t.record_days(ANN, (date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3), date(2026, 6, 4)))
    ann = t.total_deficit(ANN, asof)
    bo = t.total_deficit(BO, asof)
    cai = t.total_deficit(CAI, asof)
    assert ann < 0  # over fair share -> negative (less boost)
    assert bo > 0 and cai > 0  # below fair share -> positive (boost)
    assert ann + bo + cai == pytest.approx(0.0)


def test_total_deficit_is_zero_when_everyone_equal():
    t = make()
    asof = date(2026, 6, 16)
    for p in PEOPLE:
        t.record_days(p, (date(2026, 5, 4),))
    assert t.total_deficit(ANN, asof) == pytest.approx(0.0)


# --- FTE-weighted fair share -----------------------------------------------


def test_no_fte_reproduces_equal_split():
    """Omitting FTE weights gives every person weight 1.0 (equal split)."""
    plain = Tallies.empty(PEOPLE, SETTINGS)
    weighted = Tallies.empty(PEOPLE, SETTINGS, fte={p: 1.0 for p in PEOPLE})
    asof = date(2026, 6, 16)
    days = (date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3))
    for t in (plain, weighted):
        t.record_days(ANN, days)
    for p in PEOPLE:
        assert plain.total_deficit(p, asof) == pytest.approx(weighted.total_deficit(p, asof))


def test_fte_target_is_proportional_to_weight():
    """A half-FTE person's fair-share target is half a full-FTE person's."""
    # Ann full-time, Bo full-time, Cai half-time. 6 shift-days total.
    t = Tallies.empty(PEOPLE, SETTINGS, fte={ANN: 1.0, BO: 1.0, CAI: 0.5})
    asof = date(2026, 6, 16)
    t.record_days(ANN, (date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3)))
    t.record_days(BO, (date(2026, 6, 8), date(2026, 6, 9), date(2026, 6, 10)))
    # Targets: total 6 over weights {1,1,0.5}=2.5 -> Ann/Bo 2.4 each, Cai 1.2.
    assert t.total_deficit(ANN, asof) == pytest.approx(6 * 1.0 / 2.5 - 3)
    assert t.total_deficit(CAI, asof) == pytest.approx(6 * 0.5 / 2.5 - 0)
    # Cai (half-time, did nothing) is below her smaller target; still a boost.
    assert t.total_deficit(CAI, asof) > 0


def test_fte_deficits_still_sum_to_zero():
    t = Tallies.empty(PEOPLE, SETTINGS, fte={ANN: 1.0, BO: 0.75, CAI: 0.5})
    asof = date(2026, 6, 16)
    t.record_days(ANN, (date(2026, 6, 1), date(2026, 6, 2)))
    t.record_days(BO, (date(2026, 6, 8),))
    total = sum(t.total_deficit(p, asof) for p in PEOPLE)
    assert total == pytest.approx(0.0)


def test_full_timer_reaches_zero_deficit_at_twice_a_half_timers_load():
    """A full-timer carrying 2x a half-timer's load is fair (both zero deficit)."""
    t = Tallies.empty((ANN, CAI), SETTINGS, fte={ANN: 1.0, CAI: 0.5})
    asof = date(2026, 6, 16)
    # Ann (full) 2 days, Cai (half) 1 day -> proportional to weight -> fair.
    t.record_days(ANN, (date(2026, 6, 1), date(2026, 6, 2)))
    t.record_days(CAI, (date(2026, 6, 8),))
    assert t.total_deficit(ANN, asof) == pytest.approx(0.0)
    assert t.total_deficit(CAI, asof) == pytest.approx(0.0)


def test_non_positive_fte_is_rejected():
    with pytest.raises(ValueError, match="positive"):
        Tallies.empty(PEOPLE, SETTINGS, fte={ANN: 0.0})
    with pytest.raises(ValueError, match="positive"):
        Tallies.empty(PEOPLE, SETTINGS, fte={BO: -0.5})
