"""Tests for io/fte — the FTE (target-dedication) tab adapter.

Pure: hand-built cell grids, no gspread. We assert the percent/fraction value
parsing (and its ambiguity rule), the two-column layout, blank-row skipping, and
duplicate-name rejection.
"""

import pytest

from shift_proposer.io.fte import (
    FteLayout,
    parse_fte_grid,
    parse_fte_value,
)
from shift_proposer.models import Person

ANN = Person("Ann")
BO = Person("Bo")
CAI = Person("Cai")


# --- value parsing ---------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("50%", 0.5),
        ("100%", 1.0),
        ("25%", 0.25),
        ("0.5", 0.5),  # fraction (e.g. percent cell fetched unformatted)
        ("1", 1.0),  # <= 1 -> already a fraction (full-time)
        ("50", 0.5),  # bare > 1 -> taken as a percent
        ("100", 1.0),
        ("  75%  ", 0.75),  # whitespace tolerated
    ],
)
def test_parse_fte_value_encodings(raw, expected):
    assert parse_fte_value(raw) == pytest.approx(expected)


def test_blank_value_is_none():
    assert parse_fte_value("") is None
    assert parse_fte_value("   ") is None


def test_non_numeric_value_raises():
    with pytest.raises(ValueError, match="unrecognized"):
        parse_fte_value("full-time")


def test_non_positive_value_raises():
    with pytest.raises(ValueError, match="positive"):
        parse_fte_value("0%")
    with pytest.raises(ValueError, match="positive"):
        parse_fte_value("0")


# --- grid parsing ----------------------------------------------------------


# A simple flat layout for the value/skip logic tests (name col A, FTE col B,
# data from row 0, no blank-name terminator) — keeps these grids small.
FLAT = FteLayout(name_col=0, fte_col=1, first_data_row=0, stop_on_blank_name=False)


def test_parse_grid_default_layout_matches_stats_supsci_tab():
    # Shape of the live "Stats - SupSci" tab: name col A, FTE col I (index 8),
    # people from row 6, a blank terminator row, then a footnote row below it.
    blank = [""] * 9
    rows = [
        ["Summit Support Scientists"] + [""] * 8,  # row 1: title
        blank,  # row 2
        ["Name", "Initials", "", "", "", "", "", "Used", "Target Fraction of Time"],  # row 3
        blank,  # row 4
        ["", "", "", "10 hours / shift"] + [""] * 5,  # row 5: unit note
        ["Ann", "AN", "", "", "", "", "", "0.33", "0.5"],  # row 6 (unformatted 0.5)
        ["Bo", "BO", "", "", "", "", "", "0.21", "1"],  # row 7 (full-time)
        [""] * 9,  # row 8: blank -> roster ends here
        ["Footnote: people in bold ...", "", "", "", "", "", "", "", "0.99"],  # row 9
    ]
    assert parse_fte_grid(rows) == {ANN: 0.5, BO: 1.0}


def test_blank_name_row_ends_the_roster_by_default():
    rows = [
        ["Ann", "100%"],
        ["", "50%"],  # blank name -> stop; nothing below is read
        ["Cai", "50%"],
    ]
    layout = FteLayout(name_col=0, fte_col=1, first_data_row=0)  # stop_on_blank default
    assert parse_fte_grid(rows, layout=layout) == {ANN: 1.0}


def test_blank_value_row_is_skipped_but_roster_continues():
    rows = [
        ["Ann", "100%"],
        ["Bo", ""],  # name present, no FTE -> skipped (defaults to 1.0), continue
        ["Cai", "50%"],
    ]
    assert parse_fte_grid(rows, layout=FLAT) == {ANN: 1.0, CAI: 0.5}


def test_parse_grid_rejects_duplicate_name():
    rows = [
        ["Ann", "100%"],
        ["Ann", "50%"],
    ]
    with pytest.raises(ValueError, match="duplicate"):
        parse_fte_grid(rows, layout=FLAT)


def test_parse_grid_custom_layout():
    # Name in col B, FTE in col C, data from row 1 (no header).
    layout = FteLayout(name_col=1, fte_col=2, first_data_row=0, stop_on_blank_name=False)
    rows = [
        ["x", "Ann", "100%"],
        ["x", "Bo", "0.5"],
    ]
    assert parse_fte_grid(rows, layout=layout) == {ANN: 1.0, BO: 0.5}


def test_empty_grid_is_empty_map():
    assert parse_fte_grid([["Name", "FTE"]]) == {}
