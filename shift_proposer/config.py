"""Tunable policy for the shift proposer, all in one place.

``Settings`` is the single home for every policy knob — scoring weights and
the locked v1 decision flags (see CLAUDE.md). The engine reads values off a
``Settings`` instance; nothing about policy is scattered through the code.

This module may read the environment (it is at the package edge, not in
``engine/``) to pull the spreadsheet id, which must never be committed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date

from shift_proposer.models import Code

# Codes that collapse to plain "available" (summit-vs-remote ignored, and an
# unanswered "-" is assumed available). "?" is eligible but penalized; "X" is a
# hard block. Kept module-level so it can serve as a frozen default.
AVAILABLE_CODES: frozenset[Code] = frozenset({Code.A, Code.AS, Code.AR, Code.DASH})

# How a run treats the shifts already on the sheet within the proposal window.
# The proposal is deterministic — same inputs, same result — so these are not
# "re-roll" options; they change *which dates the engine is free to decide*.
MODE_COMPLETE = "complete"  # keep existing in-window shifts, only fill the gaps (default)
MODE_REBUILD = "rebuild"  # reopen the whole window and re-propose every date from scratch
PROPOSAL_MODES = (MODE_COMPLETE, MODE_REBUILD)


@dataclass(frozen=True)
class Settings:
    """All tunable policy for a proposal run.

    Weights are starting points to tune once there are real numbers; spacing is
    measured in days, so ``w_spacing`` is deliberately smaller than the others.
    """

    # --- shift / rest shape ------------------------------------------------
    shift_len: int = 4  # ideal block length; a run is chopped into shift_len blocks
    # Smallest block to still propose for a leftover run shorter than shift_len
    # (so short shifts get covered, not dropped). 1 = cover everything down to a
    # single night; set to shift_len to require full blocks only.
    min_shift_len: int = 1
    min_rest_rotations: int = 2  # hard rule: >= 2 rotations since last shift

    # --- availability policy ----------------------------------------------
    available_codes: frozenset[Code] = field(default_factory=lambda: AVAILABLE_CODES)

    # --- hours accounting (utilization report only; does not affect picks) -
    # A single shift-day is this many hours. The tool standardises on 12 h/shift
    # throughout; kept configurable so a different figure is a one-line change.
    hours_per_shift: float = 12.0
    # Full-time working hours per week, the denominator for "fraction of working
    # hours spent on shifts" (matches the sheet's `Used Fraction of Time`, which
    # divides by weeks × 40 h regardless of a person's FTE).
    fulltime_hours_per_week: float = 40.0

    # --- scoring weights ---------------------------------------------------
    w_total: float = 1.0  # below fair-share of total shifts (YTD)
    w_weekend: float = 1.0  # below fair-share of weekends (YTD + quarter)
    w_spacing: float = 0.1  # days since last shift (maximize rest)
    w_question: float = 0.5  # penalty per "?" day in the block

    # --- locked v1 decision flags -----------------------------------------
    block_align: str = "float"  # blocks float freely, no weekday anchor
    quarter_mode: str = "calendar"  # fairness over YTD AND calendar quarter
    quarter_seed: str = "carry_deviation"  # seed quarter from prior quarter
    output_target: str = "proposed_column"  # review-first, never live rows

    # --- run window --------------------------------------------------------
    window_start: date | None = None
    window_end: date | None = None
    # How to treat existing in-window shifts: "complete" fills only the gaps
    # (default); "rebuild" reopens the whole window and re-proposes every date.
    mode: str = MODE_COMPLETE

    # --- data source (identifiers loaded from env, never committed) --------
    sheet_id: str | None = None
    tab_name: str = "SupSci"
    # FTE (target-dedication) tab; None disables FTE weighting (equal split).
    fte_tab_name: str | None = None
    # Output tab to write the proposed calendar into (a SupSci-shaped duplicate,
    # never the live SupSci tab); None disables the in-sheet writeback.
    proposal_tab_name: str | None = None
    # Token written into a person's shift row for each proposed date (matches how
    # the live sheet marks a summit-support shift).
    proposal_token: str = "S"

    @classmethod
    def from_env(cls, **overrides) -> Settings:
        """Build settings, pulling the spreadsheet id from ``SHIFT_SHEET_ID``.

        Explicit keyword ``overrides`` win over the environment so tests and
        the CLI can inject values without touching the process environment.
        """
        env_sheet_id = os.environ.get("SHIFT_SHEET_ID")
        if env_sheet_id is not None and "sheet_id" not in overrides:
            overrides["sheet_id"] = env_sheet_id
        return cls(**overrides)
