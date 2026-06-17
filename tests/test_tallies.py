"""Step-2 tests for engine/tallies — the two-horizon counters.

All pure: hand-built people + dates, no Sheets, no network. We assert the
quarter helpers, horizon filtering (YTD vs calendar quarter), last-shift
tracking, fair-share deficits, and the carry_deviation quarter seeding.
"""

from dataclasses import replace
from datetime import date

import pytest

from shift_proposer.config import Settings
from shift_proposer.engine.tallies import (
    Tallies,
    previous_quarter,
    quarter_of,
)
from shift_proposer.models import Block, Person

ANN = Person("Ann")
BO = Person("Bo")
CAI = Person("Cai")
PEOPLE = (ANN, BO, CAI)

SETTINGS = Settings()


def make() -> Tallies:
    return Tallies.empty(PEOPLE, SETTINGS)


# --- quarter helpers -------------------------------------------------------


def test_quarter_of_maps_months_to_calendar_quarters():
    assert quarter_of(date(2026, 1, 15)) == (2026, 1)
    assert quarter_of(date(2026, 3, 31)) == (2026, 1)
    assert quarter_of(date(2026, 4, 1)) == (2026, 2)
    assert quarter_of(date(2026, 7, 1)) == (2026, 3)
    assert quarter_of(date(2026, 12, 31)) == (2026, 4)


def test_previous_quarter_wraps_year_boundary():
    assert previous_quarter((2026, 2)) == (2026, 1)
    assert previous_quarter((2026, 1)) == (2025, 4)


# --- recording & basic counters -------------------------------------------


def test_empty_tallies_have_zero_counts_and_no_last_shift():
    t = make()
    asof = date(2026, 6, 16)
    assert t.shift_days(ANN, 2026) == 0
    assert t.weekend_days(ANN, 2026) == 0
    assert t.last_shift(ANN) is None
    assert t.days_since_last_shift(ANN, asof) is None


def test_record_block_counts_shift_days_and_updates_last_shift():
    t = make()
    # Fri-Mon: 4 shift-days, 2 of them weekend (Sat 13, Sun 14).
    block = Block(
        dates=(date(2026, 6, 12), date(2026, 6, 13), date(2026, 6, 14), date(2026, 6, 15))
    )
    t.record_block(ANN, block)
    assert t.shift_days(ANN, 2026) == 4
    assert t.weekend_days(ANN, 2026) == 2
    assert t.last_shift(ANN) == date(2026, 6, 15)


def test_record_is_idempotent_on_duplicate_days():
    t = make()
    days = (date(2026, 6, 13), date(2026, 6, 14))
    t.record_days(ANN, days)
    t.record_days(ANN, days)  # same days again — must not double-count
    assert t.weekend_days(ANN, 2026) == 2


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


# --- weekend deficit & quarter carry-over ----------------------------------


def test_weekend_deficit_combines_ytd_and_quarter_horizons():
    t = make()
    asof = date(2026, 5, 16)  # Q2
    # Ann took both weekend days this quarter; others none.
    t.record_days(ANN, (date(2026, 5, 9), date(2026, 5, 10)))  # Sat, Sun (Q2)
    ann = t.weekend_deficit(ANN, asof)
    bo = t.weekend_deficit(BO, asof)
    assert ann < bo  # Ann is over-served on weekends -> lower deficit


def test_carry_deviation_seeds_quarter_from_prior_quarter_imbalance():
    """A person over-served on weekends in Q1 should start Q2 disadvantaged."""
    t = make()
    asof_q2 = date(2026, 4, 6)  # Q2, before anyone works in Q2
    # Q1 imbalance: Ann did 2 weekend-days, Bo/Cai did 0.
    t.record_days(ANN, (date(2026, 3, 14), date(2026, 3, 15)))  # Sat, Sun (Q1)

    ann = t.weekend_deficit(ANN, asof_q2)
    bo = t.weekend_deficit(BO, asof_q2)
    # YTD: Ann is over (2 vs 0) -> ytd term lower for Ann.
    # Quarter (Q2) raw counts are all 0, but carry_deviation seeds Ann high,
    # so the quarter term also disfavors Ann. Both push Ann below Bo.
    assert ann < bo


def test_quarter_seed_zero_ignores_prior_quarter_in_quarter_term():
    t = make()
    settings_zero = replace(SETTINGS, quarter_seed="zero")
    t_zero = Tallies.empty(PEOPLE, settings_zero)
    asof_q2 = date(2026, 4, 6)
    days = (date(2026, 3, 14), date(2026, 3, 15))  # Q1 weekend for Ann
    t.record_days(ANN, days)
    t_zero.record_days(ANN, days)

    # With carry_deviation the prior-quarter imbalance still tilts the quarter
    # term; with zero seeding the Q2 quarter term is flat across people.
    spread_carry = t.weekend_deficit(ANN, asof_q2) - t.weekend_deficit(BO, asof_q2)
    spread_zero = t_zero.weekend_deficit(ANN, asof_q2) - t_zero.weekend_deficit(BO, asof_q2)
    assert spread_carry < spread_zero <= 0
