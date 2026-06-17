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

from shift_proposer.config import Settings
from shift_proposer.engine.greedy import propose
from shift_proposer.io.sheets import load_fte, load_sheet
from shift_proposer.models import AvailabilityGrid, Person, Proposal
from shift_proposer.output.proposal import render_report
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


def _report_fte_coverage(people: tuple[Person, ...], fte: dict[Person, float]) -> None:
    """Warn about name-join gaps between the FTE tab and the roster (stderr).

    The person name is the join key between the two tabs, so a typo silently
    drops a weight. Surface both directions: roster members with no FTE entry
    (they default to weight 1.0) and FTE names that match no roster member.
    """
    missing = [p.name for p in people if p not in fte]
    if missing:
        print(
            f"FTE: no entry for {', '.join(missing)} — defaulting to 1.0 (full-time).",
            file=sys.stderr,
        )
    roster = set(people)
    unmatched = [p.name for p in fte if p not in roster]
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
        _report_fte_coverage(parsed.grid.people, fte)

    grid = select_window(parsed.grid, settings.window_start, settings.window_end)
    return propose(grid, settings, existing=parsed.existing, fte=fte)


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
    if args.window_start:
        overrides["window_start"] = args.window_start
    if args.window_end:
        overrides["window_end"] = args.window_end
    return Settings.from_env(**overrides)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = _settings_from_args(args)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
