"""Interpret the raw SupSci cell grid into the pure domain model.

This is an *adapter* at the I/O edge — but it is deliberately kept free of
``gspread`` so it can be unit-tested against hand-built cell grids. It takes the
raw grid (a list of rows of strings, exactly what ``gspread.get_all_values()``
returns) and produces an :class:`AvailabilityGrid` plus the assignments already
on the sheet (``Mapping[Person, list[date]]`` — the shape
:func:`engine.greedy.propose` expects for its ``existing`` argument).

Real SupSci layout (1-indexed as seen in the sheet; see :class:`LayoutConfig`
for the 0-indexed values this module uses):

* **Column A** — person name, merged vertically across that person's two rows.
* **Column B** — person initials (used elsewhere as the "who is covering"
  token); merged vertically. Captured but unused by v1 logic.
* **Column C** — per-row ``Avail`` / ``Shift`` label. Used as the roster gate:
  a real availability row carries ``Avail`` here, which is how we tell a
  scientist's row from sentinel/divider rows (``Science Support``, ``(keep these
  rows empty)``) that also have text in column A.
* **Column D onward** — the calendar, one date per column, to the sheet's end.
* **Row 1** — month header (merged per month). Ignored.
* **Row 2** — the date for each calendar column.
* **Row 3** — weekday label. Ignored (we derive weekday from the date).
* **Row 4** — count of available people that day (counts ``AS``/``AR`` only,
  which differs from our availability model). Ignored.
* **Row 5** — initials of whoever covers each day (a summary). Ignored; we read
  each person's own shift row instead.
* **Row 6 onward** — two rows per person: the **availability** row then the
  **shift** row. Person *k* occupies rows ``6 + 2*(k-1)`` and the next.

Dates: the date row's encoding is resolved by :func:`parse_date_row`, which
accepts ISO text (``YYYY-MM-DD``) or a Google Sheets serial number. A bare
day-of-month (e.g. ``"1"``) is intentionally rejected as ambiguous — supply
resolved ``dates`` explicitly (see :func:`parse_grid`) until the real encoding is
confirmed against the live sheet.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

from shift_proposer.models import AvailabilityGrid, Code, Person

# Google Sheets / Excel serial-date epoch (day 1 == 1899-12-31).
_SHEETS_EPOCH = date(1899, 12, 30)
# Below this, a numeric date cell is treated as an ambiguous day-of-month, not a
# serial (real serials are ~46000 for 2026; days-of-month are 1..31).
_MIN_SERIAL = 1000


@dataclass(frozen=True)
class LayoutConfig:
    """0-indexed positions of the fixed SupSci structure.

    Defaults match the live sheet (see module docstring). Kept configurable so a
    layout change is a constructor tweak, not a code edit.
    """

    date_row: int = 1  # row 2: the calendar dates
    first_person_row: int = 5  # row 6: first person's availability row
    rows_per_person: int = 2  # availability row + shift row
    name_col: int = 0  # column A
    initials_col: int = 1  # column B (captured, unused in v1)
    label_col: int = 2  # column C: per-row "Avail"/"Shift" marker
    first_date_col: int = 3  # column D: first calendar column
    avail_label: str = "Avail"  # marks a real availability row; "" disables the gate


# Module-level default so it is not constructed in a function signature (B008).
_DEFAULT_LAYOUT = LayoutConfig()


@dataclass(frozen=True)
class ParsedSheet:
    """The parser's output: the availability grid plus existing assignments."""

    grid: AvailabilityGrid
    existing: dict[Person, list[date]] = field(default_factory=dict)


def _cell(rows: Sequence[Sequence[str]], r: int, c: int) -> str:
    """Safe accessor: the stripped cell at ``(r, c)`` or ``""`` if out of range."""
    if r < 0 or r >= len(rows):
        return ""
    row = rows[r]
    if c < 0 or c >= len(row):
        return ""
    return row[c].strip()


def _parse_date(raw: str) -> date | None:
    """Resolve one date-header cell. ``None`` for a blank (end of calendar).

    Accepts ISO ``YYYY-MM-DD`` text or a Sheets serial number. Raises
    ``ValueError`` for an unrecognized or ambiguous (day-of-month) value.
    """
    token = raw.strip()
    if not token:
        return None
    # ISO text first — unambiguous.
    try:
        return date.fromisoformat(token)
    except ValueError:
        pass
    # Otherwise a numeric serial (UNFORMATTED_VALUE from gspread).
    try:
        serial = int(float(token))
    except ValueError:
        raise ValueError(f"unrecognized date header {raw!r}") from None
    if serial < _MIN_SERIAL:
        raise ValueError(
            f"ambiguous date header {raw!r}: looks like a day-of-month, not a "
            "serial date. Pass resolved dates explicitly to parse_grid()."
        )
    return _SHEETS_EPOCH + timedelta(days=serial)


def parse_date_row(cells: Sequence[str]) -> list[date]:
    """Resolve the calendar dates from the date row, left to right.

    Stops at the first blank cell (the end of the calendar).
    """
    dates: list[date] = []
    for cell in cells:
        day = _parse_date(cell)
        if day is None:
            break
        dates.append(day)
    return dates


def _is_assigned(cell: str) -> bool:
    """True if a shift-row cell records an assignment (non-empty, not ``-``)."""
    return bool(cell) and cell != "-"


def _is_person_row(rows: Sequence[Sequence[str]], r: int, layout: LayoutConfig) -> bool:
    """True if row ``r`` is a real person's availability row.

    Requires a non-empty name and, when ``layout.avail_label`` is set, the
    ``Avail`` marker in the label column. The marker is what distinguishes a
    scientist's row from sentinel/divider rows that also carry text in column A
    (e.g. ``Science Support``, ``(keep these rows empty)``).
    """
    if not _cell(rows, r, layout.name_col):
        return False
    if not layout.avail_label:
        return True
    return _cell(rows, r, layout.label_col).casefold() == layout.avail_label.casefold()


def parse_grid(
    rows: Sequence[Sequence[str]],
    *,
    dates: Sequence[date] | None = None,
    layout: LayoutConfig | None = None,
) -> ParsedSheet:
    """Parse the raw SupSci cell grid into a :class:`ParsedSheet`.

    ``dates`` may be supplied already-resolved (recommended until the live date
    encoding is confirmed); otherwise they are read from the date row via
    :func:`parse_date_row`. Person rows are identified by the ``Avail`` marker in
    the label column (see :func:`_is_person_row`); non-person rows are skipped, so
    sentinel/divider rows never become phantom candidates.
    """
    layout = layout or _DEFAULT_LAYOUT
    if dates is None:
        date_cells = (
            rows[layout.date_row][layout.first_date_col :] if layout.date_row < len(rows) else []
        )
        dates = parse_date_row(list(date_cells))
    dates = tuple(dates)

    people: list[Person] = []
    codes: dict[tuple[Person, date], Code] = {}
    existing: dict[Person, list[date]] = {}

    for r in range(layout.first_person_row, len(rows), layout.rows_per_person):
        if not _is_person_row(rows, r, layout):
            continue
        person = Person(name=_cell(rows, r, layout.name_col))
        people.append(person)

        avail_row = r
        shift_row = r + 1
        assigned: list[date] = []
        for offset, day in enumerate(dates):
            col = layout.first_date_col + offset
            code = Code.parse(_cell(rows, avail_row, col))
            if code is not Code.DASH:
                # DASH is the model default; only store meaningful codes.
                codes[(person, day)] = code
            if _is_assigned(_cell(rows, shift_row, col)):
                assigned.append(day)
        if assigned:
            existing[person] = assigned

        r += layout.rows_per_person

    grid = AvailabilityGrid(people=tuple(people), dates=dates, codes=codes)
    return ParsedSheet(grid=grid, existing=existing)
