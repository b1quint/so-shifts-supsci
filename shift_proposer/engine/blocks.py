"""Enumerate the unfilled blocks the proposer will try to fill.

Pure: no ``gspread``, no filesystem. Given the window of candidate dates and
the set of dates already assigned on the sheet, produce ``shift_len``-day
:class:`Block` objects over the *unfilled* dates, in date order.

Blocks float freely — no weekday anchor (``Settings.block_align == "float"``).
A block spans *consecutive calendar days*, so a run of unfilled dates is broken
by either an already-filled date or a calendar gap. Each run is chopped into
``shift_len``-day blocks front to back; a leftover shorter than ``shift_len`` is
still emitted as a **short block** (a shorter shift) as long as it is at least
``min_shift_len`` days — so short gaps get covered rather than dropped. Set
``min_shift_len == shift_len`` to require full blocks only.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from datetime import date

from shift_proposer.models import Block


def enumerate_blocks(
    dates: Iterable[date],
    filled: Collection[date],
    shift_len: int,
    min_shift_len: int = 1,
) -> list[Block]:
    """Return unfilled blocks over ``dates``, in date order.

    ``dates`` is the candidate window (any order; deduplicated here). ``filled``
    is the set of dates that already carry an assignment and must not be
    proposed over. Runs of consecutive unfilled calendar days are chopped front
    to back into ``shift_len``-day blocks; a leftover run shorter than
    ``shift_len`` is still emitted as a short block when it is at least
    ``min_shift_len`` days (otherwise that small tail is left uncovered).
    """
    filled = set(filled)
    runs = _consecutive_unfilled_runs(sorted(set(dates)), filled)

    blocks: list[Block] = []
    for run in runs:
        start = 0
        n = len(run)
        while start < n:
            length = min(shift_len, n - start)
            if length < min_shift_len:
                break  # remaining tail is too short to cover
            blocks.append(Block(dates=tuple(run[start : start + length])))
            start += length
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
