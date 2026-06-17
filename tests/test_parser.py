"""Step-4 tests for io/parser — raw SupSci grid -> domain model.

Pure: hand-built cell grids (list[list[str]]), no gspread. We assert the date
resolution (ISO + serial + ambiguity rejection), the two-rows-per-person layout,
availability-code mapping (A/AS/AR/- collapse, ? and X preserved), existing
assignment detection from the shift row, and roster termination on a blank name.
"""

from datetime import date

import pytest

from shift_proposer.io.parser import (
    LayoutConfig,
    index_grid,
    parse_date_row,
    parse_grid,
)
from shift_proposer.models import Code, Person

D1 = date(2026, 6, 1)
D2 = date(2026, 6, 2)
D3 = date(2026, 6, 3)
DATES = [D1, D2, D3]

ANN = Person("Ann")
BO = Person("Bo")

# A realistic small grid matching the live layout: rows 0-4 are header/summary
# (mostly ignored), people begin at row index 5 with two rows each. Calendar
# starts at column index 3 (column D).
GRID = [
    ["", "", "", "June", "", ""],  # row 1: month header (ignored)
    ["", "", "", "2026-06-01", "2026-06-02", "2026-06-03"],  # row 2: dates
    ["", "", "", "Mon", "Tue", "Wed"],  # row 3: weekday (ignored)
    ["", "", "", "2", "1", "0"],  # row 4: avail count (ignored)
    ["", "", "", "AB", "", ""],  # row 5: shift summary (ignored)
    ["Ann", "AB", "avail", "A", "AS", "X"],  # row 6: Ann availability
    ["", "", "shift", "", "ROLE", ""],  # row 7: Ann shift -> assigned D2
    ["Bo", "BC", "avail", "?", "-", "A"],  # row 8: Bo availability
    ["", "", "shift", "BC", "", "-"],  # row 9: Bo shift -> assigned D1
    ["", "", "", "", "", ""],  # row 10: blank name -> roster ends
]


# --- date resolution -------------------------------------------------------


def test_parse_date_row_reads_iso_until_blank():
    cells = ["2026-06-01", "2026-06-02", "", "2026-06-04"]
    assert parse_date_row(cells) == [D1, D2]  # stops at the blank


def test_parse_date_row_reads_serial_numbers():
    serial = (D1 - date(1899, 12, 30)).days
    assert parse_date_row([str(serial)]) == [D1]


def test_bare_day_of_month_is_rejected_as_ambiguous():
    with pytest.raises(ValueError, match="ambiguous"):
        parse_date_row(["1", "2", "3"])


# --- full grid parse -------------------------------------------------------


def test_people_are_read_in_row_order():
    parsed = parse_grid(GRID)
    assert parsed.grid.people == (ANN, BO)


def test_dates_resolved_from_the_date_row():
    parsed = parse_grid(GRID)
    assert parsed.grid.dates == tuple(DATES)


def test_availability_codes_mapped_with_dash_as_default():
    parsed = parse_grid(GRID)
    g = parsed.grid
    assert g.code(ANN, D1) is Code.A
    assert g.code(ANN, D2) is Code.AS
    assert g.code(ANN, D3) is Code.X
    assert g.code(BO, D1) is Code.QUESTION
    assert g.code(BO, D2) is Code.DASH  # "-" collapses to the default
    assert g.code(BO, D3) is Code.A


def test_existing_assignments_come_from_the_shift_row():
    parsed = parse_grid(GRID)
    assert parsed.existing == {ANN: [D2], BO: [D1]}  # "-" / blank are not assignments


def test_explicit_dates_override_the_date_row():
    # Caller supplies resolved dates; the date row is then irrelevant.
    explicit = [date(2030, 1, 1), date(2030, 1, 2), date(2030, 1, 3)]
    parsed = parse_grid(GRID, dates=explicit)
    assert parsed.grid.dates == tuple(explicit)
    assert parsed.grid.code(ANN, explicit[2]) is Code.X


# --- layout index (for writeback) ------------------------------------------


def test_index_grid_maps_shift_rows_and_date_columns():
    idx = index_grid(GRID)
    # Ann's avail row is index 5 -> shift row 6; Bo's avail 7 -> shift 8.
    assert idx.shift_row_by_name == {"Ann": 6, "Bo": 8}
    # Dates start at column D (index 3), one per column.
    assert idx.col_by_date == {D1: 3, D2: 4, D3: 5}


def test_roster_stops_at_first_blank_name():
    # Append a stray person *after* the blank divider row; it must be ignored.
    grid = [list(r) for r in GRID]
    grid.append(["Cai", "CD", "avail", "A", "A", "A"])
    parsed = parse_grid(grid)
    assert Person("Cai") not in parsed.grid.people


def test_custom_layout_is_honored():
    # A trimmed grid with no header rows and the calendar at column index 1.
    # avail_label="" disables the label gate (there is no label column here).
    layout = LayoutConfig(date_row=0, first_person_row=1, first_date_col=1, avail_label="")
    grid = [
        ["", "2026-06-01", "2026-06-02"],
        ["Ann", "A", "X"],
        ["", "", "DONE"],  # Ann shift -> assigned D2
    ]
    parsed = parse_grid(grid, layout=layout)
    assert parsed.grid.people == (ANN,)
    assert parsed.grid.code(ANN, D2) is Code.X
    assert parsed.existing == {ANN: [date(2026, 6, 2)]}


def test_sentinel_rows_without_avail_label_are_not_people():
    # Mirrors the live sheet: a divider row carries a name in column A but no
    # "Avail" marker in column C, and must never become a phantom candidate.
    grid = [
        ["", "", "", "2026-06-01", "2026-06-02", "2026-06-03"],  # row 0: dates
        ["", "", "", "", "", ""],
        ["", "", "", "", "", ""],
        ["", "", "", "", "", ""],
        ["", "", "", "", "", ""],
        ["Ann", "AB", "Avail", "A", "A", "A"],  # real person
        ["", "", "Shift", "", "", ""],
        ["(keep these rows empty)", "-", "", "", "", ""],  # sentinel: no "Avail"
        ["", "!", "", "X", "X", "X"],  # its "shift" row would otherwise fill dates
    ]
    layout = LayoutConfig(date_row=0)
    parsed = parse_grid(grid, layout=layout)
    assert parsed.grid.people == (ANN,)
    assert Person("(keep these rows empty)") not in parsed.grid.people
    assert parsed.existing == {}  # the sentinel's row must not fill any date


def test_out_label_excludes_a_person_from_the_rotation():
    # A real, named person marked "Out": kept in the sheet but not scheduled,
    # not counted, and reported in `inactive`. Their shift row must not fill dates.
    grid = [
        ["", "", "", "2026-06-01", "2026-06-02", "2026-06-03"],  # row 0: dates
        ["", "", "", "", "", ""],
        ["", "", "", "", "", ""],
        ["", "", "", "", "", ""],
        ["", "", "", "", "", ""],
        ["Ann", "AB", "Avail", "A", "A", "A"],  # active rotation member
        ["", "", "Shift", "", "", ""],
        ["Brian", "BS", "Out", "A", "A", "A"],  # covers shifts, not in rotation
        ["", "", "Shift", "BS", "BS", "BS"],  # his coverage must NOT count as filled
    ]
    parsed = parse_grid(grid, layout=LayoutConfig(date_row=0))
    assert parsed.grid.people == (ANN,)
    assert parsed.inactive == (Person("Brian"),)
    assert parsed.existing == {}  # Brian's shift row does not fill any date
