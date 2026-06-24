"""Command-line entrypoint — wire the adapter, engine, and output together.

The flow is a straight line: build :class:`Settings` (pulling the spreadsheet id
from the environment) → read + parse the SupSci tab (:mod:`io.sheets`) → restrict
to the run window → propose (:func:`engine.greedy.propose`) → print the review
report and write the CSV (:mod:`output`).

Only :func:`main` reaches the network (via ``load_sheet``); the wiring helpers
take an injectable ``client`` and pure inputs so the pipeline is testable without
auth. This module owns no scheduling logic — it just connects the pieces.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

from shift_proposer.config import MODE_REBUILD, PROPOSAL_MODES, Settings
from shift_proposer.engine.greedy import propose
from shift_proposer.engine.report import (
    SORT_FTE,
    SORT_MODES,
    SORT_SHEET,
    ShiftReportRow,
    build_report,
)
from shift_proposer.io.sheets import load_fte, load_sheet, write_proposal_calendar
from shift_proposer.models import AvailabilityGrid, Person, Proposal
from shift_proposer.output.proposal import render_report
from shift_proposer.output.report import render_report as render_shift_report
from shift_proposer.output.report import write_report_csv
from shift_proposer.output.writeback import write_csv


def select_window(
    grid: AvailabilityGrid,
    start: date | None,
    end: date | None,
) -> AvailabilityGrid:
    """Restrict ``grid`` to dates within ``[start, end]`` (either bound optional).

    Codes outside the window are left in the mapping (harmless — only the kept
    dates are ever queried), so this only narrows which dates get proposed.
    """
    if start is None and end is None:
        return grid
    dates = tuple(
        day for day in grid.dates if (start is None or day >= start) and (end is None or day <= end)
    )
    return replace(grid, dates=dates)


def _report_fte_coverage(
    people: tuple[Person, ...],
    fte: dict[Person, float],
    inactive: tuple[Person, ...] = (),
) -> None:
    """Warn about name-join gaps between the FTE tab and the roster (stderr).

    The person name is the join key between the two tabs, so a typo silently
    drops a weight. Surface both directions: roster members with no FTE entry
    (they default to weight 1.0) and FTE names that match no *active* person.
    People explicitly marked ``Out`` (``inactive``) are expected to be absent
    from the rotation, so an FTE entry for them is not flagged as a mismatch.
    """
    missing = [p.name for p in people if p not in fte]
    if missing:
        print(
            f"FTE: no entry for {', '.join(missing)} — defaulting to 1.0 (full-time).",
            file=sys.stderr,
        )
    known = set(people) | set(inactive)
    unmatched = [p.name for p in fte if p not in known]
    if unmatched:
        print(
            f"FTE: {', '.join(unmatched)} in the FTE tab match no roster member "
            "(ignored — check for a name mismatch).",
            file=sys.stderr,
        )


def propose_from_sheet(settings: Settings, *, client=None) -> Proposal:
    """Read SupSci (and the FTE tab if configured) and return a :class:`Proposal`.

    ``client`` is injectable so this whole pipeline can run against a fake sheet
    in tests; production passes ``None`` and OAuth runs inside ``load_sheet``.
    When ``settings.fte_tab_name`` is set, fair share is FTE-weighted; otherwise
    it is an equal split.
    """
    parsed = load_sheet(settings, client=client)
    if parsed.inactive:
        names = ", ".join(p.name for p in parsed.inactive)
        print(f"Excluded from rotation (marked Out): {names}", file=sys.stderr)

    fte: dict[Person, float] | None = None
    if settings.fte_tab_name:
        fte = load_fte(settings, client=client)
        _report_fte_coverage(parsed.grid.people, fte, parsed.inactive)

    grid = select_window(parsed.grid, settings.window_start, settings.window_end)
    no_shift = [d for d in parsed.no_shift if d in set(grid.dates)]
    if no_shift:
        print(
            f"No-shift dates in window (skipped): {len(no_shift)} "
            f"({min(no_shift).isoformat()} … {max(no_shift).isoformat()})",
            file=sys.stderr,
        )
    return propose(
        grid,
        settings,
        existing=parsed.existing,
        fte=fte,
        no_shift=parsed.no_shift,
        mode=settings.mode,
    )


def _sheet_window(
    grid: AvailabilityGrid, start: date | None, end: date | None
) -> tuple[date, date]:
    """Resolve the report window, defaulting to the sheet's full date range.

    A missing ``--window-start`` / ``--window-end`` falls back to the first /
    last calendar date present on the sheet, so the unbounded report covers
    everything. Raises ``ValueError`` if the sheet has no dates at all.
    """
    if not grid.dates:
        raise ValueError("the sheet has no calendar dates to report on")
    return (start or grid.dates[0], end or grid.dates[-1])


def report_from_sheet(
    settings: Settings, *, sort_by: str = SORT_SHEET, client=None
) -> tuple[list[ShiftReportRow], date, date]:
    """Read SupSci's existing shifts and summarise per person over the window.

    Read-only: it never proposes or writes. Returns the rows plus the resolved
    ``(start, end)`` so the caller can title the output. ``client`` is injectable
    for testing without auth (mirrors :func:`propose_from_sheet`).

    ``sort_by`` orders the rows (``"sheet"`` keeps the spreadsheet order;
    ``"fte"`` ranks by target FTE). When ``settings.fte_tab_name`` is set the FTE
    tab is loaded and shown; ``sort_by="fte"`` requires it (raises ``ValueError``
    otherwise, since there is nothing to rank by).
    """
    parsed = load_sheet(settings, client=client)

    fte: dict[Person, float] | None = None
    if settings.fte_tab_name:
        fte = load_fte(settings, client=client)
        _report_fte_coverage(parsed.grid.people, fte, parsed.inactive)
    elif sort_by == SORT_FTE:
        raise ValueError("--sort fte requires an FTE tab; pass --fte-tab NAME.")

    start, end = _sheet_window(parsed.grid, settings.window_start, settings.window_end)
    rows = build_report(
        parsed.grid.people,
        parsed.existing,
        start=start,
        end=end,
        settings=settings,
        fte=fte,
        sort_by=sort_by,
    )
    return rows, start, end


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="shift-proposer",
        description="Propose a shift calendar from the SupSci availability sheet.",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("proposal.csv"),
        help="path to write the proposal CSV (default: proposal.csv)",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="report existing shifts per person (days, weekends, %% of working "
        "hours at 12 h/shift) instead of proposing — read-only, never writes",
    )
    parser.add_argument(
        "--report-csv",
        type=Path,
        help="with --report, also write the report to this CSV path",
    )
    parser.add_argument(
        "--sort",
        choices=SORT_MODES,
        default=SORT_SHEET,
        help="with --report, row order: 'sheet' (spreadsheet order, default) or "
        "'fte' (rank by target FTE %%, highest first; requires --fte-tab)",
    )
    parser.add_argument(
        "--sheet-id",
        help="spreadsheet id (overrides SHIFT_SHEET_ID)",
    )
    parser.add_argument(
        "--tab",
        help="worksheet/tab name (default: SupSci)",
    )
    parser.add_argument(
        "--fte-tab",
        help="tab holding per-person target FTE %% (enables FTE-weighted fair share)",
    )
    parser.add_argument(
        "--out-tab",
        help="SupSci-shaped duplicate tab to write the proposed calendar into "
        "(fills empty shift cells; never the live SupSci tab)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="with --out-tab, show how many cells would be written without writing",
    )
    parser.add_argument(
        "--mode",
        choices=PROPOSAL_MODES,
        default=None,
        help="how to treat existing shifts in the window: 'complete' (default) "
        "fills only the empty dates; 'rebuild' reopens the whole window and "
        "re-proposes every date from scratch",
    )
    parser.add_argument(
        "--window-start",
        type=date.fromisoformat,
        help="earliest date to propose (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--window-end",
        type=date.fromisoformat,
        help="latest date to propose (YYYY-MM-DD)",
    )
    return parser.parse_args(argv)


def _settings_from_args(args: argparse.Namespace) -> Settings:
    overrides: dict[str, object] = {}
    if args.sheet_id:
        overrides["sheet_id"] = args.sheet_id
    if args.tab:
        overrides["tab_name"] = args.tab
    if args.fte_tab:
        overrides["fte_tab_name"] = args.fte_tab
    if args.out_tab:
        overrides["proposal_tab_name"] = args.out_tab
    if args.mode:
        overrides["mode"] = args.mode
    if args.window_start:
        overrides["window_start"] = args.window_start
    if args.window_end:
        overrides["window_end"] = args.window_end
    return Settings.from_env(**overrides)


def _run_report(settings: Settings, report_csv: Path | None, sort_by: str) -> int:
    """Print the per-person shift-utilization report; optionally write a CSV."""
    try:
        rows, start, end = report_from_sheet(settings, sort_by=sort_by)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(render_shift_report(rows, start=start, end=end))
    if report_csv is not None:
        out = write_report_csv(rows, report_csv)
        print(f"\nWrote report for {len(rows)} person(s) to {out}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = _settings_from_args(args)

    if args.report:
        return _run_report(settings, args.report_csv, args.sort)

    try:
        proposal = propose_from_sheet(settings)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(render_report(proposal))
    out = write_csv(proposal, args.csv)
    print(
        f"\nWrote {len(proposal.assignments)} assignment(s), "
        f"{len(proposal.unfilled)} unfilled, to {out}",
        file=sys.stderr,
    )

    if settings.proposal_tab_name:
        if settings.mode == MODE_REBUILD:
            print(
                "warning: --mode rebuild re-proposes dates that may already hold "
                f"real shift assignments in tab {settings.proposal_tab_name!r}; "
                "those cells will not be overwritten — clear the window first if "
                "you want a clean rebuild in the proposal tab.",
                file=sys.stderr,
            )
        try:
            updates = write_proposal_calendar(settings, proposal, dry_run=args.dry_run)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        verb = "Would write" if args.dry_run else "Wrote"
        print(
            f"{verb} {len(updates)} cell(s) into tab {settings.proposal_tab_name!r}.",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
