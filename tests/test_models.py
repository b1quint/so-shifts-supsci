"""Step-1 sanity tests for the pure domain types and Settings.

The heavy, test-first logic lands in step 2 (engine/tallies). These just lock
in the value-object behavior the engine will rely on.
"""

from datetime import date

from shift_proposer.config import AVAILABLE_CODES, Settings
from shift_proposer.models import (
    AvailabilityGrid,
    Block,
    Code,
    Person,
    Proposal,
)


def test_code_parse_collapses_blank_and_unknown_to_dash():
    assert Code.parse(None) is Code.DASH
    assert Code.parse("") is Code.DASH
    assert Code.parse("   ") is Code.DASH
    assert Code.parse("junk") is Code.DASH


def test_code_parse_is_case_and_whitespace_insensitive():
    assert Code.parse(" as ") is Code.AS
    assert Code.parse("x") is Code.X
    assert Code.parse("?") is Code.QUESTION


def test_person_is_hashable_for_stable_keying():
    grid = {Person("Ann"): 1, Person("Bo"): 2}
    assert grid[Person("Ann")] == 1


def test_availability_grid_defaults_missing_to_dash():
    ann = Person("Ann")
    day = date(2026, 6, 16)
    grid = AvailabilityGrid(people=(ann,), dates=(day,), codes={(ann, day): Code.X})
    assert grid.code(ann, day) is Code.X
    assert grid.code(ann, date(2026, 6, 17)) is Code.DASH  # unspecified


def test_block_reports_start_end_and_weekend_days():
    # 2026-06-12 is a Friday; 13 Sat, 14 Sun, 15 Mon.
    block = Block(
        dates=(date(2026, 6, 12), date(2026, 6, 13), date(2026, 6, 14), date(2026, 6, 15))
    )
    assert block.start == date(2026, 6, 12)
    assert block.end == date(2026, 6, 15)
    assert block.weekend_days() == (date(2026, 6, 13), date(2026, 6, 14))


def test_settings_defaults_match_locked_v1_decisions():
    s = Settings()
    assert s.shift_len == 4
    assert s.min_rest_rotations == 2
    assert s.available_codes == AVAILABLE_CODES == {Code.A, Code.AS, Code.AR, Code.DASH}
    assert s.block_align == "float"
    assert s.quarter_mode == "calendar"
    assert s.quarter_seed == "carry_deviation"
    assert s.output_target == "proposed_column"
    assert s.tab_name == "SupSci"


def test_settings_from_env_reads_sheet_id(monkeypatch):
    monkeypatch.setenv("SHIFT_SHEET_ID", "abc123")
    assert Settings.from_env().sheet_id == "abc123"
    # explicit override wins over the environment
    assert Settings.from_env(sheet_id="explicit").sheet_id == "explicit"


def test_empty_proposal_has_no_assignments_or_unfilled():
    p = Proposal()
    assert p.assignments == ()
    assert p.unfilled == ()
