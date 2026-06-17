"""Interpret the FTE (target-dedication) tab into per-person weights.

A second adapter at the I/O edge, kept free of ``gspread`` so it is unit-testable
against hand-built cell grids. It reads a simple two-column tab — a person's name
and their target FTE (fraction of full-time dedicated to shifts) — and produces a
``dict[Person, float]`` suitable for :func:`engine.greedy.propose`'s ``fte``
argument, where fair share is made proportional to the weight.

Default layout (1-indexed as seen in the sheet; see :class:`FteLayout` for the
0-indexed values used here):

* **Column A** — person name. Must match the SupSci name exactly: the name is the
  join key between the two tabs.
* **Column B** — target FTE, written as a percent (``50%``, ``100%``).
* **Row 1** — header. Ignored.
* **Row 2 onward** — one person per row.

FTE values are parsed by :func:`parse_fte_value`, which accepts ``"50%"`` as well
as the bare number Google Sheets stores behind a percent cell (``0.5`` when
fetched unformatted) and a bare percent (``50`` → ``0.5``). The result is always a
0-1 fraction. Blank-name or blank-value rows are skipped; a duplicate name is an
error (an FTE tab should list each person once).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from shift_proposer.models import Person


@dataclass(frozen=True)
class FteLayout:
    """0-indexed positions of the FTE tab's structure.

    Defaults: name in column A, FTE in column B, data from row 2 (row 1 is a
    header). Kept configurable so a layout change is a constructor tweak.
    """

    name_col: int = 0  # column A
    fte_col: int = 1  # column B
    first_data_row: int = 1  # row 2 (row 1 is a header)


# Module-level default so it is not constructed in a function signature (B008).
_DEFAULT_FTE_LAYOUT = FteLayout()


def _cell(rows: Sequence[Sequence[str]], r: int, c: int) -> str:
    """Safe accessor: the stripped cell at ``(r, c)`` or ``""`` if out of range."""
    if r < 0 or r >= len(rows):
        return ""
    row = rows[r]
    if c < 0 or c >= len(row):
        return ""
    return row[c].strip()


def parse_fte_value(raw: str) -> float | None:
    """Resolve one FTE cell into a 0-1 fraction. ``None`` for a blank cell.

    Accepts three encodings so it is robust to how the cell is fetched/typed:

    * ``"50%"`` / ``"100%"`` — explicit percent → divide by 100.
    * ``"0.5"`` / ``"1"`` — a value ``<= 1`` is taken as already a fraction
      (this is what a percent-formatted cell returns when fetched *unformatted*).
    * ``"50"`` — a bare value ``> 1`` is taken as a percent → divide by 100.

    Raises ``ValueError`` for a non-numeric value or a non-positive result (an
    FTE of zero or less has no meaningful fair share).
    """
    token = raw.strip()
    if not token:
        return None
    is_percent = token.endswith("%")
    if is_percent:
        token = token[:-1].strip()
    try:
        value = float(token)
    except ValueError:
        raise ValueError(f"unrecognized FTE value {raw!r}") from None
    fraction = value / 100.0 if is_percent or value > 1.0 else value
    if fraction <= 0:
        raise ValueError(f"FTE must be positive; got {raw!r}")
    return fraction


def parse_fte_grid(
    rows: Sequence[Sequence[str]],
    *,
    layout: FteLayout | None = None,
) -> dict[Person, float]:
    """Parse the raw FTE cell grid into ``{Person: weight}``.

    Rows with a blank name or a blank FTE value are skipped (a person absent from
    the result defaults to weight ``1.0`` downstream). A name appearing twice is a
    ``ValueError``.
    """
    layout = layout or _DEFAULT_FTE_LAYOUT
    result: dict[Person, float] = {}
    for r in range(layout.first_data_row, len(rows)):
        name = _cell(rows, r, layout.name_col)
        raw = _cell(rows, r, layout.fte_col)
        if not name or not raw:
            continue
        person = Person(name=name)
        if person in result:
            raise ValueError(f"duplicate FTE entry for {name!r}")
        value = parse_fte_value(raw)
        if value is not None:
            result[person] = value
    return result
