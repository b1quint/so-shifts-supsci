"""Step-6 tests for cli — the wiring, exercised without the network.

A fake gspread client (reused shape from test_sheets) feeds a hand-built SupSci
grid through the whole pipeline: sheets -> parser -> engine -> Proposal. We also
assert window selection (pure) and argument parsing. Live OAuth in ``main`` is
not tested.
"""

from datetime import date

from shift_proposer.cli import (
    parse_args,
    propose_from_sheet,
    select_window,
)
from shift_proposer.config import Settings
from shift_proposer.models import AvailabilityGrid, Person

ANN = Person("Ann")
BO = Person("Bo")


# --- fakes (no network) ----------------------------------------------------


class FakeWorksheet:
    def __init__(self, values):
        self._values = values

    def get_all_values(self, **kwargs):
        return self._values


class FakeSpreadsheet:
    def __init__(self, worksheet):
        self._worksheet = worksheet

    def worksheet(self, name):
        return self._worksheet


class FakeClient:
    def __init__(self, values):
        self._spreadsheet = FakeSpreadsheet(FakeWorksheet(values))

    def open_by_key(self, key):
        return self._spreadsheet


# A minimal SupSci grid: 4 consecutive available dates, two people, no prior
# assignments -> exactly one 4-day block.
SHEET = [
    ["", "", "", "", "", "", ""],  # row 1: month header
    ["", "", "", "2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04"],  # row 2: dates
    ["", "", "", "", "", "", ""],  # row 3: weekday
    ["", "", "", "", "", "", ""],  # row 4: avail count
    ["", "", "", "", "", "", ""],  # row 5: shift summary
    ["Ann", "AB", "avail", "", "", "", ""],  # row 6: Ann availability (all available)
    ["", "", "shift", "", "", "", ""],  # row 7: Ann shift (none)
    ["Bo", "BC", "avail", "", "", "", ""],  # row 8: Bo availability
    ["", "", "shift", "", "", "", ""],  # row 9: Bo shift (none)
    ["", "", "", "", "", "", ""],  # row 10: blank name -> end
]


# --- window selection (pure) -----------------------------------------------


def _grid(dates):
    return AvailabilityGrid(people=(ANN,), dates=tuple(dates), codes={})


def test_select_window_no_bounds_returns_grid_unchanged():
    grid = _grid([date(2026, 6, 1), date(2026, 6, 2)])
    assert select_window(grid, None, None) is grid


def test_select_window_filters_to_bounds_inclusive():
    days = [date(2026, 6, d) for d in (1, 2, 3, 4, 5)]
    grid = _grid(days)
    narrowed = select_window(grid, date(2026, 6, 2), date(2026, 6, 4))
    assert narrowed.dates == (date(2026, 6, 2), date(2026, 6, 3), date(2026, 6, 4))


# --- full pipeline through a fake sheet ------------------------------------


def test_propose_from_sheet_runs_end_to_end():
    settings = Settings(sheet_id="SHEET123")
    proposal = propose_from_sheet(settings, client=FakeClient(SHEET))
    # One block; tie between two never-assigned people resolves to lowest name.
    assert len(proposal.assignments) == 1
    assert proposal.assignments[0].person == ANN
    assert proposal.assignments[0].block.dates[0] == date(2026, 6, 1)
    assert proposal.unfilled == ()


# --- FTE-weighted fair share (end-to-end through the FTE tab) ---------------


class FakeMultiTabClient:
    """A fake client serving a different grid per tab name."""

    def __init__(self, by_tab):
        self._by_tab = by_tab

    def open_by_key(self, key):
        client = self

        class _SS:
            def worksheet(self, name):
                return FakeWorksheet(client._by_tab[name])

        return _SS()


# History (4 consecutive *weekdays*, so no weekend term) then an open weekday
# block. Ann already took 3 of the 4 history days, Bo 1 -> on an equal split Bo
# is further behind and wins the open block. Under a 90/10 FTE split Ann's target
# is high enough that she is the one behind, so the pick flips to her.
FTE_SHEET = [
    ["", "", "", "", "", "", "", "", "", "", ""],  # month header
    # Mon-Thu history (May 4-7) then Mon-Thu open block (Jun 1-4) — no weekends.
    [
        "",
        "",
        "",
        "2026-05-04",
        "2026-05-05",
        "2026-05-06",
        "2026-05-07",
        "2026-06-01",
        "2026-06-02",
        "2026-06-03",
        "2026-06-04",
    ],  # fmt: skip
    ["", "", "", "", "", "", "", "", "", "", ""],  # weekday
    ["", "", "", "", "", "", "", "", "", "", ""],  # avail count
    ["", "", "", "", "", "", "", "", "", "", ""],  # shift summary
    ["Ann", "AB", "avail", "", "", "", "", "", "", "", ""],  # Ann availability
    ["", "", "shift", "x", "x", "x", "", "", "", "", ""],  # Ann: May 4,5,6 assigned
    ["Bo", "BC", "avail", "", "", "", "", "", "", "", ""],  # Bo availability
    ["", "", "shift", "", "", "", "x", "", "", "", ""],  # Bo: May 7 assigned
    ["", "", "", "", "", "", "", "", "", "", ""],  # end
]

# Default FTE layout: name col A, FTE col I (index 8), people from row 6.
_FTE_BLANK = [""] * 9
FTE_TAB = [
    _FTE_BLANK,
    _FTE_BLANK,
    ["Name", "", "", "", "", "", "", "", "Target Fraction of Time"],
    _FTE_BLANK,
    _FTE_BLANK,
    ["Ann", "", "", "", "", "", "", "", "90%"],
    ["Bo", "", "", "", "", "", "", "", "10%"],
]


def test_fte_tab_flips_the_pick_vs_equal_split():
    window = dict(window_start=date(2026, 6, 1), window_end=date(2026, 6, 4))
    client = FakeMultiTabClient({"SupSci": FTE_SHEET, "FTE": FTE_TAB})

    # Equal split (no FTE tab): Bo is furthest behind -> Bo wins the open block.
    equal = propose_from_sheet(Settings(sheet_id="S", **window), client=client)
    assert [a.person for a in equal.assignments] == [BO]

    # FTE-weighted (Ann 90%, Bo 10%): Ann's target outweighs her history -> Ann.
    weighted = propose_from_sheet(
        Settings(sheet_id="S", fte_tab_name="FTE", **window), client=client
    )
    assert [a.person for a in weighted.assignments] == [ANN]


def test_propose_from_sheet_honors_the_window():
    # Window keeps only 3 of the 4 dates -> one short (3-day) block over exactly
    # those dates (short shifts are allowed; the 4th date is outside the window).
    settings = Settings(
        sheet_id="SHEET123",
        window_start=date(2026, 6, 1),
        window_end=date(2026, 6, 3),
    )
    proposal = propose_from_sheet(settings, client=FakeClient(SHEET))
    assert len(proposal.assignments) == 1
    assert proposal.assignments[0].block.dates == (
        date(2026, 6, 1),
        date(2026, 6, 2),
        date(2026, 6, 3),
    )
    assert proposal.unfilled == ()


# --- argument parsing ------------------------------------------------------


def test_parse_args_defaults():
    args = parse_args([])
    assert args.csv.name == "proposal.csv"
    assert args.sheet_id is None
    assert args.window_start is None


def test_parse_args_reads_window_and_sheet_id():
    args = parse_args(
        ["--sheet-id", "XYZ", "--window-start", "2026-06-01", "--window-end", "2026-06-30"]
    )
    assert args.sheet_id == "XYZ"
    assert args.window_start == date(2026, 6, 1)
    assert args.window_end == date(2026, 6, 30)


def test_parse_args_reads_fte_tab():
    assert parse_args([]).fte_tab is None
    assert parse_args(["--fte-tab", "FTE"]).fte_tab == "FTE"


def test_parse_args_reads_out_tab_and_dry_run():
    defaults = parse_args([])
    assert defaults.out_tab is None
    assert defaults.dry_run is False
    args = parse_args(["--out-tab", "SupSci Shift Proposal", "--dry-run"])
    assert args.out_tab == "SupSci Shift Proposal"
    assert args.dry_run is True
