"""gspread + OAuth adapter — the SupSci tab as a raw cell grid.

This is the **only** module that imports ``gspread`` or touches the network. It
reads the SupSci worksheet and hands back a plain ``list[list[str]]`` grid; all
interpretation lives in :mod:`io.parser` (pure) so the engine never sees Sheets.

Auth is OAuth *user* credentials via :func:`gspread.oauth` — authorize once in a
browser, after which the token is cached on disk (default
``~/.config/gspread/``). No service account, no sheet sharing; the user owns the
sheet. The spreadsheet id is never hard-coded — it comes from
``Settings.sheet_id`` (loaded from ``SHIFT_SHEET_ID``).

Cells are fetched **unformatted** (``UNFORMATTED_VALUE``) so a real date cell
comes back as its serial number, which :func:`io.parser.parse_date_row` resolves
unambiguously. Values are stringified here so the parser only ever sees strings.
"""

from __future__ import annotations

from typing import Any, Protocol

import gspread
from gspread.utils import ValueRenderOption

from shift_proposer.config import Settings
from shift_proposer.io.fte import parse_fte_grid
from shift_proposer.io.parser import ParsedSheet, index_grid, parse_grid
from shift_proposer.models import Person, Proposal
from shift_proposer.output.writeback import CellUpdate, plan_calendar_fill


class _Worksheet(Protocol):
    """The slice of the gspread worksheet API this module relies on."""

    def get_all_values(self, **kwargs: Any) -> list[list[Any]]: ...


def _stringify(value: Any) -> str:
    """Render one fetched cell as a string (``None``/blank -> ``""``)."""
    if value is None:
        return ""
    return str(value)


def fetch_grid(worksheet: _Worksheet) -> list[list[str]]:
    """Return the worksheet as a stringified grid, dates as serial numbers.

    Pure given a worksheet, so it is unit-testable with a fake. Merged name /
    initials cells return their value only in the merge's top-left cell, which is
    each person's availability (top) row — exactly where the parser reads it.
    """
    raw = worksheet.get_all_values(value_render_option=ValueRenderOption.unformatted)
    return [[_stringify(cell) for cell in row] for row in raw]


def authorize(settings: Settings) -> gspread.Client:
    """Return an OAuth gspread client (cached token; one-time browser consent)."""
    return gspread.oauth()


def open_worksheet(
    client: gspread.Client, settings: Settings, tab_name: str | None = None
) -> gspread.Worksheet:
    """Open a tab by name (default ``settings.tab_name``); require a sheet id."""
    if not settings.sheet_id:
        raise ValueError("settings.sheet_id is required (set SHIFT_SHEET_ID).")
    spreadsheet = client.open_by_key(settings.sheet_id)
    return spreadsheet.worksheet(tab_name or settings.tab_name)


def read_raw_grid(settings: Settings, *, client: gspread.Client | None = None) -> list[list[str]]:
    """Authorize (unless a ``client`` is injected), open SupSci, fetch the grid."""
    # Validate before touching OAuth so a missing id fails fast and clearly,
    # rather than surfacing a credentials error from the auth flow.
    if not settings.sheet_id:
        raise ValueError("settings.sheet_id is required (set SHIFT_SHEET_ID).")
    client = client or authorize(settings)
    worksheet = open_worksheet(client, settings)
    return fetch_grid(worksheet)


def load_sheet(settings: Settings, *, client: gspread.Client | None = None) -> ParsedSheet:
    """Read SupSci and parse it into the domain model — the adapter entrypoint."""
    return parse_grid(read_raw_grid(settings, client=client))


def read_fte_grid(settings: Settings, *, client: gspread.Client | None = None) -> list[list[str]]:
    """Authorize (unless a ``client`` is injected), open the FTE tab, fetch it."""
    if not settings.sheet_id:
        raise ValueError("settings.sheet_id is required (set SHIFT_SHEET_ID).")
    if not settings.fte_tab_name:
        raise ValueError("settings.fte_tab_name is required to load FTE weights.")
    client = client or authorize(settings)
    worksheet = open_worksheet(client, settings, settings.fte_tab_name)
    return fetch_grid(worksheet)


def load_fte(settings: Settings, *, client: gspread.Client | None = None) -> dict[Person, float]:
    """Read the FTE tab and parse it into ``{Person: weight}``."""
    return parse_fte_grid(read_fte_grid(settings, client=client))


def plan_proposal_calendar(
    rows: list[list[str]], proposal: Proposal, settings: Settings
) -> list[CellUpdate]:
    """Plan the cells to fill in a SupSci-shaped grid for ``proposal`` (pure).

    Indexes ``rows`` (the duplicate tab read as a raw grid) and fills only empty
    shift cells. Separated from the network apply so it is unit-testable.
    """
    idx = index_grid(rows)

    proposal_token = settings.proposal_token

    def is_empty(r: int, c: int) -> bool:
        if r >= len(rows) or c >= len(rows[r]):
            return True
        cell = rows[r][c].strip()
        # Treat a cell already holding the proposal token as overwriteable so
        # re-running the tool doesn't silently write 0 cells.  Cells with any
        # other value (real shift assignments) are left untouched.
        return cell == "" or cell == proposal_token

    return plan_calendar_fill(
        proposal,
        shift_row_by_name=idx.shift_row_by_name,
        col_by_date=idx.col_by_date,
        is_empty=is_empty,
        token=settings.proposal_token,
    )


def write_proposal_calendar(
    settings: Settings,
    proposal: Proposal,
    *,
    client: gspread.Client | None = None,
    dry_run: bool = False,
) -> list[CellUpdate]:
    """Write ``proposal`` into the proposal tab's calendar; return the updates.

    Reads the proposal tab as a raw grid, plans which empty shift cells to fill
    (:func:`plan_proposal_calendar`), and applies them in one batch. Refuses to
    write to the live ``SupSci`` tab — the target must be a separate duplicate.
    With ``dry_run`` the planned updates are returned but nothing is written.
    """
    if not settings.sheet_id:
        raise ValueError("settings.sheet_id is required (set SHIFT_SHEET_ID).")
    if not settings.proposal_tab_name:
        raise ValueError("settings.proposal_tab_name is required to write the calendar.")
    if settings.proposal_tab_name == settings.tab_name:
        raise ValueError(
            f"refusing to write into the live tab {settings.tab_name!r}; "
            "proposal_tab_name must be a separate duplicate."
        )

    client = client or authorize(settings)
    worksheet = open_worksheet(client, settings, settings.proposal_tab_name)
    rows = fetch_grid(worksheet)
    updates = plan_proposal_calendar(rows, proposal, settings)
    if updates and not dry_run:
        cells = [gspread.Cell(row=u.row + 1, col=u.col + 1, value=u.value) for u in updates]
        worksheet.update_cells(cells)
    return updates
