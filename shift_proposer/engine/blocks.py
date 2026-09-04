"""Enumerate the unfilled blocks the proposer will try to fill.

Pure: no ``gspread``, no filesystem. Given the window of candidate dates and
the set of dates already assigned on the sheet, produce ``shift_len``-day
:class:`Block` objects over the *unfilled* dates, in date order.

By default blocks float freely — no weekday anchor. A block spans *consecutive
calendar days*, so a run of unfilled dates is broken by either an already-filled
date or a calendar gap. Each run is chopped into ``shift_len``-day blocks front
to back; a leftover shorter than ``shift_len`` is still emitted as a **short
block** (a shorter shift) as long as it is at least ``min_shift_len`` days — so
short gaps get covered rather than dropped. Set ``min_shift_len == shift_len``
to require full blocks only.

Passing ``anchor_weekday`` (``Settings.block_align == "monday"`` -> ``0``) pins
every full-length block to start on that weekday: a run is first split at its
first occurrence of ``anchor_weekday`` into a leading short block (the days
before the run reaches that weekday) and the remainder, which is then chopped
into ``shift_len``-day blocks as usual — since ``shift_len`` days from an
anchored start lands on the same weekday again, every subsequent full block
stays anchored automatically.
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
    anchor_weekday: int | None = None,
) -> list[Block]:
    """Return unfilled blocks over ``dates``, in date order.

    ``dates`` is the candidate window (any order; deduplicated here). ``filled``
    is the set of dates that already carry an assignment and must not be
    proposed over. Runs of consecutive unfilled calendar days are chopped front
    to back into ``shift_len``-day blocks; a leftover run shorter than
    ``shift_len`` is still emitted as a short block when it is at least
    ``min_shift_len`` days (otherwise that small tail is left uncovered).

    ``anchor_weekday`` (0=Monday .. 6=Sunday), when given, pins every full block
    to start on that weekday; see the module docstring.
    """
    filled = set(filled)
    runs = _consecutive_unfilled_runs(sorted(set(dates)), filled)

    blocks: list[Block] = []
    for run in runs:
        n = len(run)
        start = 0
        if anchor_weekday is not None:
            anchor_index = next(
                (i for i, day in enumerate(run) if day.weekday() == anchor_weekday), n
            )
            if anchor_index > 0 and anchor_index >= min_shift_len:
                blocks.append(Block(dates=tuple(run[:anchor_index])))
            start = anchor_index
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
