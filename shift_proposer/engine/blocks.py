"""Enumerate the unfilled blocks the proposer will try to fill.

Pure: no ``gspread``, no filesystem. Given the window of candidate dates and
the set of dates already assigned on the sheet, produce ``shift_len``-day
:class:`Block` objects over the *unfilled* dates, in date order.

Blocks float freely — no weekday anchor (``Settings.block_align == "float"``).
A block must span ``shift_len`` *consecutive calendar days*, so a run of
unfilled dates is broken by either an already-filled date or a calendar gap.
A trailing run shorter than ``shift_len`` forms no block (it is left
uncovered); the design works in whole ``shift_len``-day shifts.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from datetime import date

from shift_proposer.models import Block


def enumerate_blocks(
    dates: Iterable[date],
    filled: Collection[date],
    shift_len: int,
) -> list[Block]:
    """Return unfilled ``shift_len``-day blocks over ``dates``, in date order.

    ``dates`` is the candidate window (any order; deduplicated here). ``filled``
    is the set of dates that already carry an assignment and must not be
    proposed over. Runs of consecutive unfilled calendar days are chopped into
    consecutive full blocks; remainders shorter than ``shift_len`` are dropped.
    """
    filled = set(filled)
    runs = _consecutive_unfilled_runs(sorted(set(dates)), filled)

    blocks: list[Block] = []
    for run in runs:
        for start in range(0, len(run) - shift_len + 1, shift_len):
            blocks.append(Block(dates=tuple(run[start : start + shift_len])))
    return blocks


def _consecutive_unfilled_runs(
    ordered_dates: list[date],
    filled: set[date],
) -> list[list[date]]:
    """Split ordered, deduped dates into maximal consecutive-unfilled runs."""
    runs: list[list[date]] = []
    current: list[date] = []
    prev: date | None = None

    for day in ordered_dates:
        if day in filled:
            if current:
                runs.append(current)
            current = []
        elif current and prev is not None and (day - prev).days == 1:
            current.append(day)
        else:
            if current:
                runs.append(current)
            current = [day]
        prev = day

    if current:
        runs.append(current)
    return runs
