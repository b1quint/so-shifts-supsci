"""Step-4 tests for io/sheets — the gspread adapter, without the network.

We never hit OAuth or Google here: fakes stand in for the gspread client /
spreadsheet / worksheet. We assert that cells are stringified, that the
unformatted render option is requested (so dates arrive as serials), that the
spreadsheet id / tab name are threaded through, and that a missing id is a clear
error. Live auth (``authorize``) is intentionally untested.
"""

from datetime import date, timedelta

import pytest
from gspread.utils import ValueRenderOption

from shift_proposer.config import Settings
from shift_proposer.io.sheets import (
    apply_live_calendar,
    fetch_grid,
    load_fte,
    open_worksheet,
    plan_proposal_calendar,
    read_fte_grid,
    read_raw_grid,
    write_proposal_calendar,
)
from shift_proposer.models import Assignment, Block, Person, Proposal, Rationale


class FakeWorksheet:
    def __init__(self, values):
        self._values = values
        self.last_kwargs = None

    def get_all_values(self, **kwargs):
        self.last_kwargs = kwargs
        return self._values


class FakeSpreadsheet:
    def __init__(self, worksheet):
        self._worksheet = worksheet
        self.requested_tab = None

    def worksheet(self, name):
        self.requested_tab = name
        return self._worksheet


class FakeClient:
    def __init__(self, spreadsheet):
        self._spreadsheet = spreadsheet
        self.opened_key = None

    def open_by_key(self, key):
        self.opened_key = key
        return self._spreadsheet


def test_fetch_grid_stringifies_cells_and_requests_unformatted():
    # Mixed types as gspread returns under UNFORMATTED_VALUE: serial ints, text,
    # empty cells.
    ws = FakeWorksheet([[46184, "AS", ""], ["Ann", None, "X"]])
    grid = fetch_grid(ws)
    assert grid == [["46184", "AS", ""], ["Ann", "", "X"]]
    assert ws.last_kwargs == {"value_render_option": ValueRenderOption.unformatted}


def test_open_worksheet_requires_a_sheet_id():
    with pytest.raises(ValueError, match="sheet_id is required"):
        open_worksheet(client=None, settings=Settings(sheet_id=None))


def test_open_worksheet_threads_id_and_tab_name():
    ws = FakeWorksheet([])
    spreadsheet = FakeSpreadsheet(ws)
    client = FakeClient(spreadsheet)
    settings = Settings(sheet_id="SHEET123", tab_name="SupSci")

    result = open_worksheet(client, settings)

    assert result is ws
    assert client.opened_key == "SHEET123"
    assert spreadsheet.requested_tab == "SupSci"


def test_read_raw_grid_validates_id_before_authorizing():
    # No client injected and no sheet id: must fail fast with the clear error,
    # never reaching the OAuth flow.
    with pytest.raises(ValueError, match="sheet_id is required"):
        read_raw_grid(Settings(sheet_id=None))


def test_read_raw_grid_uses_injected_client_end_to_end():
    ws = FakeWorksheet([[46184, "A"]])
    client = FakeClient(FakeSpreadsheet(ws))
    settings = Settings(sheet_id="SHEET123")

    grid = read_raw_grid(settings, client=client)

    assert grid == [["46184", "A"]]


# --- FTE tab ---------------------------------------------------------------


class FakeMultiTabSpreadsheet:
    """A spreadsheet whose ``worksheet(name)`` returns a per-name fake."""

    def __init__(self, by_name):
        self._by_name = by_name
        self.requested_tab = None

    def worksheet(self, name):
        self.requested_tab = name
        return self._by_name[name]


def test_read_fte_grid_requires_an_fte_tab_name():
    # Sheet id present but no FTE tab configured: clear error, no OAuth.
    with pytest.raises(ValueError, match="fte_tab_name is required"):
        read_fte_grid(Settings(sheet_id="SHEET123", fte_tab_name=None))


def test_read_fte_grid_opens_the_configured_fte_tab():
    fte_ws = FakeWorksheet([["Name", "FTE"], ["Ann", "50%"]])
    spreadsheet = FakeMultiTabSpreadsheet({"FTE": fte_ws})
    client = FakeClient(spreadsheet)
    settings = Settings(sheet_id="SHEET123", fte_tab_name="FTE")

    grid = read_fte_grid(settings, client=client)

    assert grid == [["Name", "FTE"], ["Ann", "50%"]]
    assert spreadsheet.requested_tab == "FTE"


def test_load_fte_parses_to_person_weights():
    # Default layout: name col A, FTE col I (index 8), people from row 6.
    blank = [""] * 9
    grid = [
        blank,
        blank,
        ["Name", "", "", "", "", "", "", "", "Target Fraction of Time"],
        blank,
        blank,
        ["Ann", "", "", "", "", "", "", "", "100%"],
        ["Bo", "", "", "", "", "", "", "", "50%"],
    ]
    client = FakeClient(FakeMultiTabSpreadsheet({"FTE": FakeWorksheet(grid)}))
    settings = Settings(sheet_id="SHEET123", fte_tab_name="FTE")

    weights = load_fte(settings, client=client)

    assert weights == {Person("Ann"): 1.0, Person("Bo"): 0.5}


# --- writing the proposal calendar -----------------------------------------


class WritableFakeWorksheet(FakeWorksheet):
    def __init__(self, values):
        super().__init__(values)
        self.written = None

    def update_cells(self, cells):
        self.written = [(c.row, c.col, c.value) for c in cells]


# A SupSci-shaped proposal tab: dates at cols 3-6, Ann (rows 5/6), Bo (rows 7/8).
# Ann's shift row already has an assignment on day 1 (col 3).
PROP_TAB = [
    ["", "", "", "", "", "", ""],
    ["", "", "", "2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04"],
    ["", "", "", "", "", "", ""],
    ["", "", "", "", "", "", ""],
    ["", "", "", "", "", "", ""],
    ["Ann", "AN", "Avail", "", "", "", ""],
    ["", "", "Shift", "S", "", "", ""],  # day 1 already filled
    ["Bo", "BO", "Avail", "", "", "", ""],
    ["", "", "Shift", "", "", "", ""],
]


def _block(start_offsets):
    base = date(2026, 6, 1)
    return Block(dates=tuple(base + timedelta(days=i) for i in start_offsets))


def _proposal_for(person):
    rationale = Rationale(total=1.0, terms={})
    return Proposal(assignments=(Assignment(person, _block(range(4)), rationale),))


def test_plan_proposal_calendar_overwrites_existing_proposal_token():
    # A cell that already holds the proposal token (from a previous run) must be
    # overwritten so re-running the tool doesn't silently write 0 cells.
    settings = Settings(sheet_id="S", proposal_tab_name="Prop")
    updates = plan_proposal_calendar(PROP_TAB, _proposal_for(Person("Ann")), settings)
    # Ann's shift row is index 6; day-1 col 3 has "S" (proposal token) -> overwritten.
    assert [(u.row, u.col, u.value) for u in updates] == [
        (6, 3, "S"),
        (6, 4, "S"),
        (6, 5, "S"),
        (6, 6, "S"),
    ]


def test_plan_proposal_calendar_does_not_overwrite_real_shift_assignments():
    # A cell with a real shift token (anything other than the proposal token) must
    # not be overwritten — only the proposal itself writes into the proposal tab.
    prop_tab_with_real_shift = [row[:] for row in PROP_TAB]
    prop_tab_with_real_shift[6] = ["", "", "Shift", "BS", "", "", ""]  # real person
    settings = Settings(sheet_id="S", proposal_tab_name="Prop")
    updates = plan_proposal_calendar(
        prop_tab_with_real_shift, _proposal_for(Person("Ann")), settings
    )
    # col 3 has "BS" (not the proposal token) -> skipped.
    assert [(u.row, u.col) for u in updates] == [(6, 4), (6, 5), (6, 6)]


def test_write_proposal_calendar_applies_cells_through_gspread():
    ws = WritableFakeWorksheet(PROP_TAB)
    client = FakeClient(FakeMultiTabSpreadsheet({"Prop": ws}))
    settings = Settings(sheet_id="S", tab_name="SupSci", proposal_tab_name="Prop")

    updates = write_proposal_calendar(settings, _proposal_for(Person("Bo")), client=client)

    # Bo's shift row is index 8; all four days empty -> four writes (1-indexed).
    assert ws.written == [(9, 4, "S"), (9, 5, "S"), (9, 6, "S"), (9, 7, "S")]
    assert len(updates) == 4


def test_write_proposal_calendar_dry_run_writes_nothing():
    ws = WritableFakeWorksheet(PROP_TAB)
    client = FakeClient(FakeMultiTabSpreadsheet({"Prop": ws}))
    settings = Settings(sheet_id="S", proposal_tab_name="Prop")

    updates = write_proposal_calendar(
        settings, _proposal_for(Person("Bo")), client=client, dry_run=True
    )

    assert ws.written is None  # nothing applied
    assert len(updates) == 4  # but the plan is still returned


def test_write_proposal_calendar_refuses_to_write_the_live_tab():
    settings = Settings(sheet_id="S", tab_name="SupSci", proposal_tab_name="SupSci")
    with pytest.raises(ValueError, match="refusing to write into the live tab"):
        write_proposal_calendar(settings, _proposal_for(Person("Bo")), client=FakeClient(None))


# --- apply_live_calendar ---------------------------------------------------


# Same shape as PROP_TAB but represents the live SupSci tab.  Ann's shift row
# (index 6) already has "S" on day 1; Bo's row is clean.
LIVE_TAB = [
    ["", "", "", "", "", "", ""],
    ["", "", "", "2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04"],
    ["", "", "", "", "", "", ""],
    ["", "", "", "", "", "", ""],
    ["", "", "", "", "", "", ""],
    ["Ann", "AN", "Avail", "", "", "", ""],
    ["", "", "Shift", "S", "", "", ""],  # day 1 already assigned
    ["Bo", "BO", "Avail", "", "", "", ""],
    ["", "", "Shift", "", "", "", ""],
]


def test_apply_live_calendar_writes_to_live_tab():
    ws = WritableFakeWorksheet(LIVE_TAB)
    client = FakeClient(FakeMultiTabSpreadsheet({"SupSci": ws}))
    settings = Settings(sheet_id="S", tab_name="SupSci")

    updates = apply_live_calendar(settings, _proposal_for(Person("Bo")), client=client)

    # Bo's shift row (index 8) is fully empty -> four writes, 1-indexed.
    assert ws.written == [(9, 4, "S"), (9, 5, "S"), (9, 6, "S"), (9, 7, "S")]
    assert len(updates) == 4


def test_apply_live_calendar_skips_non_empty_cells_strictly():
    # Ann already has a real assignment on day 1 (col 3 holds "S").
    # Unlike the proposal-tab writer, apply_live does NOT treat the token as
    # overwriteable — existing assignments must be left alone.
    ws = WritableFakeWorksheet(LIVE_TAB)
    client = FakeClient(FakeMultiTabSpreadsheet({"SupSci": ws}))
    settings = Settings(sheet_id="S", tab_name="SupSci")

    updates = apply_live_calendar(settings, _proposal_for(Person("Ann")), client=client)

    # Day 1 col 3 has "S" -> skipped; only days 2-4 are written.
    assert [(u.row, u.col) for u in updates] == [(6, 4), (6, 5), (6, 6)]


def test_apply_live_calendar_dry_run_writes_nothing():
    ws = WritableFakeWorksheet(LIVE_TAB)
    client = FakeClient(FakeMultiTabSpreadsheet({"SupSci": ws}))
    settings = Settings(sheet_id="S", tab_name="SupSci")

    updates = apply_live_calendar(
        settings, _proposal_for(Person("Bo")), client=client, dry_run=True
    )

    assert ws.written is None
    assert len(updates) == 4
