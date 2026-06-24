"""Step-3 tests for engine/greedy — the date-ordered greedy fill.

All pure: hand-built grids + existing assignments, no Sheets. We assert the
core guarantees: under-loaded people win, the rest rule is never violated across
picks, an empty candidate pool flags the block unfilled, existing assignments
seed both 'filled' and the tallies, the tie-break is stable, and the whole run
is deterministic.
"""

from dataclasses import replace
from datetime import date, timedelta

import pytest

from shift_proposer.config import MODE_COMPLETE, MODE_REBUILD, Settings
from shift_proposer.engine.greedy import propose
from shift_proposer.models import AvailabilityGrid, Block, Code, Person

ANN = Person("Ann")
BO = Person("Bo")
CAI = Person("Cai")
PEOPLE = (ANN, BO, CAI)

MON = date(2026, 6, 1)
SETTINGS = Settings()  # shift_len=4, min_rest_rotations=2 -> 8 days rest


def days(start: date, n: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


def make_grid(dates, codes=None) -> AvailabilityGrid:
    return AvailabilityGrid(people=PEOPLE, dates=tuple(dates), codes=codes or {})


def test_no_blocks_yields_empty_proposal():
    proposal = propose(make_grid([]), SETTINGS)  # no candidate dates -> no blocks
    assert proposal.assignments == ()
    assert proposal.unfilled == ()


def test_short_run_is_covered_by_a_short_block():
    # A 2-day run is shorter than shift_len but still gets covered (min_shift_len=1).
    window = days(MON, 2)
    proposal = propose(make_grid(window), SETTINGS)
    assert len(proposal.assignments) == 1
    assert proposal.assignments[0].block.dates == tuple(window)


def test_single_block_picks_lowest_name_when_all_tied():
    # All three never-assigned and fully available -> tie -> lowest name wins.
    grid = make_grid(days(MON, 4))
    proposal = propose(grid, SETTINGS)
    assert len(proposal.assignments) == 1
    assert proposal.assignments[0].person == ANN
    assert proposal.assignments[0].block.dates == tuple(days(MON, 4))
    assert proposal.assignments[0].rationale.total == proposal.assignments[0].rationale.total


def test_rest_rule_forces_a_different_person_on_adjacent_block():
    # Two back-to-back blocks; whoever takes block 1 is rest-blocked from block 2.
    window = days(MON, 8)
    proposal = propose(make_grid(window), SETTINGS)
    assert [a.person for a in proposal.assignments] == [ANN, BO]
    assert [a.block.dates for a in proposal.assignments] == [
        tuple(window[0:4]),
        tuple(window[4:8]),
    ]
    assert proposal.unfilled == ()


def test_block_with_no_eligible_candidate_is_flagged_unfilled():
    window = days(MON, 4)
    # Everyone hard-blocked somewhere in the block.
    codes = {(p, window[0]): Code.X for p in PEOPLE}
    proposal = propose(make_grid(window, codes), SETTINGS)
    assert proposal.assignments == ()
    assert proposal.unfilled == (Block(dates=tuple(window)),)


def test_existing_assignments_seed_filled_and_load():
    window = days(MON, 8)
    # Ann already holds the first block -> it is filled, and Ann is loaded+resting.
    existing = {ANN: window[0:4]}
    proposal = propose(make_grid(window), SETTINGS, existing=existing)
    # Only the second block is open; Ann is both over-loaded and rest-blocked.
    assert len(proposal.assignments) == 1
    assert proposal.assignments[0].block.dates == tuple(window[4:8])
    assert proposal.assignments[0].person == BO


def test_underloaded_person_is_preferred():
    window = days(MON, 4)
    far_past = days(MON - timedelta(days=90), 4)  # old enough to be rested
    # Bo and Cai each already carry an old block; Ann carries none. Zero the
    # spacing weight so the fair-share load (not the 90-day rest gap) decides.
    settings = replace(SETTINGS, w_spacing=0.0)
    existing = {BO: far_past, CAI: far_past}
    proposal = propose(make_grid(window), settings, existing=existing)
    assert proposal.assignments[0].person == ANN


def test_no_shift_dates_are_excluded_not_proposed_or_flagged():
    # 8-day window; mark days 4-5 (indices 3,4) as no-shift. The surrounding
    # 3-day stretches are still covered (short blocks), but the no-shift dates
    # themselves are never proposed and never flagged.
    window = days(MON, 8)
    no_shift = [window[3], window[4]]
    proposal = propose(make_grid(window), SETTINGS, no_shift=no_shift)
    covered = {d for a in proposal.assignments for d in a.block.dates}
    flagged = {d for b in proposal.unfilled for d in b.dates}
    assert not ({window[3], window[4]} & covered)  # no-shift never proposed
    assert not ({window[3], window[4]} & flagged)  # no-shift never flagged
    assert covered == {*window[0:3], *window[5:8]}  # the two stretches are covered


def test_no_shift_only_breaks_blocks_does_not_seed_load():
    # Days 5-8 form a clean block after a 4-day no-shift period at the start.
    window = days(MON, 8)
    no_shift = window[0:4]
    proposal = propose(make_grid(window), SETTINGS, no_shift=no_shift)
    # The first four days are skipped; the second four are one normal block.
    assert len(proposal.assignments) == 1
    assert proposal.assignments[0].block.dates == tuple(window[4:8])
    # Excluded dates seed nobody, so the all-tied pick is still the lowest name.
    assert proposal.assignments[0].person == ANN


def test_run_is_deterministic():
    window = days(MON, 12)
    grid = make_grid(window)
    first = propose(grid, SETTINGS)
    second = propose(grid, SETTINGS)
    assert first == second


def test_complete_is_the_default_mode():
    # The default keeps existing in-window shifts (only the gap is filled).
    window = days(MON, 8)
    existing = {ANN: window[0:4]}
    default = propose(make_grid(window), SETTINGS, existing=existing)
    explicit = propose(make_grid(window), SETTINGS, existing=existing, mode=MODE_COMPLETE)
    assert default == explicit
    # Only the open second block is proposed; the first stays Ann's.
    assert [a.block.dates for a in default.assignments] == [tuple(window[4:8])]


def test_rebuild_reopens_in_window_existing_assignments():
    # Ann holds the first block. In rebuild, that block is reopened and re-proposed
    # alongside the second, so two assignments come back (vs one in complete mode).
    window = days(MON, 8)
    existing = {ANN: window[0:4]}
    proposal = propose(make_grid(window), SETTINGS, existing=existing, mode=MODE_REBUILD)
    assert [a.block.dates for a in proposal.assignments] == [
        tuple(window[0:4]),
        tuple(window[4:8]),
    ]
    # With everyone reset to zero load, the all-tied first block goes to Ann
    # (lowest name); the rest rule then forces Bo onto the second.
    assert [a.person for a in proposal.assignments] == [ANN, BO]


def test_rebuild_keeps_out_of_window_history_as_fairness_seed():
    # Bo and Cai each carry an old (out-of-window) block; Ann carries none. Even
    # under rebuild, that history still seeds fair share, so the under-loaded Ann
    # wins the (single) in-window block. Zero spacing so load alone decides.
    window = days(MON, 4)
    far_past = days(MON - timedelta(days=90), 4)
    settings = replace(SETTINGS, w_spacing=0.0)
    existing = {BO: far_past, CAI: far_past}
    proposal = propose(make_grid(window), settings, existing=existing, mode=MODE_REBUILD)
    assert proposal.assignments[0].person == ANN


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError, match="unknown mode"):
        propose(make_grid(days(MON, 4)), SETTINGS, mode="recalculate")


def test_out_person_covered_dates_are_treated_as_filled():
    # An "Out" person (not in grid.people) may appear in `existing` because the
    # parser now records their covered dates.  The engine must add those dates to
    # `filled` so it never proposes a rotation member on top of an Out-covered night.
    window = days(MON, 8)
    out_person = Person("Out-Brian")
    # Out-Brian covers the first block; he is NOT in grid.people.
    existing = {out_person: window[0:4]}
    proposal = propose(make_grid(window), SETTINGS, existing=existing)
    # Only the second block is open; the first is blocked by Out-Brian.
    assert len(proposal.assignments) == 1
    assert proposal.assignments[0].block.dates == tuple(window[4:8])
    # Out-Brian is not in the candidate pool, so the pick is the lowest-named
    # active person.
    assert proposal.assignments[0].person == ANN


def test_out_person_covered_dates_do_not_seed_fairness_tallies():
    # Out-Brian's covered dates block scheduling (above) but must NOT count toward
    # the active people's fair-share targets, because Out-people are excluded from
    # the average.  Verify by checking that the all-tied pick still goes to ANN
    # (lowest name) despite Out-Brian covering some nights.
    window = days(MON, 4)
    out_person = Person("Zara-Out")  # alphabetically last, not in grid.people
    far_past = days(MON - timedelta(days=90), 20)
    existing = {out_person: far_past}  # lots of out-of-window coverage
    proposal = propose(make_grid(window), SETTINGS, existing=existing)
    # If Out-Zara's nights inflated the "total shifts" used for fair-share, the
    # deficit calculation would be wrong.  With equal active tallies the pick must
    # still be ANN (name tie-break), not be distorted by the extra coverage.
    assert proposal.assignments[0].person == ANN
