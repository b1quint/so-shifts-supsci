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


def test_parse_grid_default_layout():
    rows = [
        ["Name", "FTE"],  # header (row 1) -> skipped
        ["Ann", "100%"],
        ["Bo", "50%"],
        ["Cai", "75%"],
    ]
    assert parse_fte_grid(rows) == {ANN: 1.0, BO: 0.5, CAI: 0.75}


def test_parse_grid_skips_blank_name_or_value_rows():
    rows = [
        ["Name", "FTE"],
        ["Ann", "100%"],
        ["", "50%"],  # no name -> skip
        ["Bo", ""],  # no value -> skip (defaults to 1.0 downstream)
        ["Cai", "50%"],
    ]
    assert parse_fte_grid(rows) == {ANN: 1.0, CAI: 0.5}


def test_parse_grid_rejects_duplicate_name():
    rows = [
        ["Name", "FTE"],
        ["Ann", "100%"],
        ["Ann", "50%"],
    ]
    with pytest.raises(ValueError, match="duplicate"):
        parse_fte_grid(rows)


def test_parse_grid_custom_layout():
    # Name in col B, FTE in col C, data from row 1 (no header).
    layout = FteLayout(name_col=1, fte_col=2, first_data_row=0)
    rows = [
        ["x", "Ann", "100%"],
        ["x", "Bo", "0.5"],
    ]
    assert parse_fte_grid(rows, layout=layout) == {ANN: 1.0, BO: 0.5}


def test_empty_grid_is_empty_map():
    assert parse_fte_grid([["Name", "FTE"]]) == {}
