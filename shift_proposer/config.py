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


@dataclass(frozen=True)
class Settings:
    """All tunable policy for a proposal run.

    Weights are starting points to tune once there are real numbers; spacing is
    measured in days, so ``w_spacing`` is deliberately smaller than the others.
    """

    # --- shift / rest shape ------------------------------------------------
    shift_len: int = 4
    min_rest_rotations: int = 2  # hard rule: >= 2 rotations since last shift

    # --- availability policy ----------------------------------------------
    available_codes: frozenset[Code] = field(default_factory=lambda: AVAILABLE_CODES)

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

    # --- data source (identifiers loaded from env, never committed) --------
    sheet_id: str | None = None
    tab_name: str = "SupSci"
    # FTE (target-dedication) tab; None disables FTE weighting (equal split).
    fte_tab_name: str | None = None

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
