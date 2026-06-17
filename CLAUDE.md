# Shift Calendar Proposal Generator

Python tool that reads the SupSci availability spreadsheet and produces a **proposed**
shift calendar for review. It does **not** run the live schedule — it fills currently-empty
dates and a human reviews the proposal before it becomes real.

**Source of truth for design & decisions:** the [`docs/`](docs/) folder (migrated from the
project's internal Confluence space). A single short Confluence page now just points back here.
When implementation diverges from the docs, update the relevant page in `docs/` — don't let them
drift.

Sub-tool of the Unified Scheduling Tool project; aligns with the
[`rso_shift_scheduler`](https://github.com/b1quint/rso_shift_scheduler) repo and a future
Django backend, so the scheduling logic must stay reusable (see Conventions).

---

## Current status

Design complete, **no code yet**. Build from scratch in the layout below.

## Tech & setup

- Python 3.11+, `gspread` (Google Sheets), `pandas` / `datetime`, `pytest`.
- Auth: `gspread` with **OAuth user credentials** (authorize once, token cached). No
  service account / sheet sharing — the user owns the sheet. This is the only one-time setup.
- Data source: the **Unified Summit Shifts Schedule** spreadsheet, tab **`SupSci`**.
  Supply the spreadsheet id via config/env (e.g. `SHIFT_SHEET_ID`) — **do not commit it**.
  Reference it as `<SHEET_ID>` in code/docs.
- Scope of v1: SupSci tab only; runs manually; output is a proposal, not the live schedule.

> Secrets & identifiers: keep the real spreadsheet id, OAuth client secrets, and cached tokens
> out of version control (`.gitignore` them; load from env or a local untracked config file).

## Data model (the spreadsheet)

Dates are **columns**. Each person occupies **two rows**:

- Row 1 — **availability code** per date: `A`, `AS`, `AR`, `X`, `?`, `-`
- Row 2 — **assigned shift/role** for that date, if any.

Availability handling (v1, decided): `A` / `AS` / `AR` / `-` all collapse to **"available"**
(summit-vs-remote ignored; unanswered `-` assumed available). `?` = available-but-penalized.
`X` = unavailable (hard block).

**Roster membership (column C label).** Each person row carries an `Avail` / `Shift` label in
column C; the parser uses it as the **roster gate** (this is what separates real scientists from
sentinel/divider rows like `Science Support` or `(keep these rows empty)` that also have text in
column A). A row whose label is **`Out`** is a person kept in the sheet for records but **excluded
from the rotation** — never scheduled and never counted in any fair-share average (use this for
occasional coverers who aren't official rotation members). The CLI reports who it excluded. Markers
live in `parser.LayoutConfig` (`avail_label`, `inactive_label`).

**No-shift periods (`Requires support?` row).** A per-date checkbox row labelled **`Requires
support?`** (the parser finds it by that column-A label, not a fixed index) flags nights when **no
shift runs at all** (shutdowns/engineering): a **`FALSE`** cell marks a no-shift date. Those dates are
excluded from block enumeration entirely — **neither proposed nor flagged "unfilled"** (intentionally
empty ≠ wanted-a-person-but-found-none) — and never seed the tallies. Only an explicit `FALSE` counts,
so a missing/unticked marker never silently drops a date. Lives in `parser.LayoutConfig.support_label`
(set `""` to disable). Checkboxes read as booleans (`TRUE`/`FALSE`).

**Target FTE (separate tab).** Each person has a target **FTE** (`Target Fraction of Time` — fraction
of full-time dedicated to shifts) that makes fair share proportional rather than an equal split — a
50% person targets about half the shifts of a 100% person. FTE lives in its **own tab**, the live
`Stats - SupSci`, read by the `io/fte.py` adapter: **name in column A**, **`Target Fraction of Time`
in column I**, people from **row 6** to the first blank-name row. People are keyed back to the roster
by **name** (the join key — a typo silently drops a weight, so the CLI warns on mismatches in both
directions, except for people already marked `Out`). Enabled by pointing `Settings.fte_tab_name` at
that tab (CLI `--fte-tab "Stats - SupSci"`); when unset, fair share falls back to the equal split.
Layout is configurable in `fte.FteLayout`. Note: relative fair share only depends on the *ratio* of
targets, so the shift-hours-vs-FTE-hours conversion (a global constant) does not affect who is
picked — it would only matter for an absolute expected-shift-count figure. (All targets are currently
50%, so FTE-weighting presently equals the equal split; it diverges once targets differ.)

## Architecture — pure core behind an I/O boundary

The single load-bearing decision: **`engine/` imports nothing from `gspread` or the filesystem.**
It takes plain domain objects in and returns a `Proposal` out. Sheets is one adapter at the edge.
This is what makes the logic portable to the Django backend (swap the adapter, keep the engine)
and unit-testable without auth.

```
shift_proposer/
├── cli.py            # entrypoint: build Settings, wire adapter -> engine -> output
├── config.py         # Settings dataclass: weights, shift_len=4, window, policy values
├── models.py         # PURE domain types: Person, Code(enum), AvailabilityGrid, Block,
│                     #   Assignment, Proposal, Rationale
├── io/
│   ├── sheets.py     # gspread + OAuth: SupSci + FTE tabs <-> raw cell grid (ONLY gspread import)
│   ├── parser.py     # raw grid -> AvailabilityGrid + existing Assignments; A/AS/AR/- -> available
│   └── fte.py        # raw FTE tab -> {Person: weight} (target FTE %, keyed by name)
├── engine/           # PURE. no gspread, no I/O. domain objects in, Proposal out.
│   ├── blocks.py     # enumerate unfilled blocks in window (shift_len, short tail >= min_shift_len)
│   ├── eligibility.py# hard rules: skip filled, reject any 'X', enforce >=2-rotation rest
│   ├── tallies.py    # shift-days + weekend-days on 2 horizons (YTD + calendar quarter w/
│   │                 #   carry-over); per-person last-shift date; FTE-weighted fair-share targets
│   ├── scoring.py    # score(person, block, tallies) -> float + per-term breakdown
│   └── greedy.py     # loop: block -> eligible -> score -> pick (stable tie-break) -> update
└── output/
    ├── proposal.py   # Proposal: list[Assignment] + per-pick Rationale (score trace)
    └── writeback.py  # CSV export + plan_calendar_fill (pure: proposal -> CellUpdates) — NEVER live rows
```

## Algorithm (greedy + scoring)

```
# runs of consecutive unfilled days are chopped into shift_len blocks; a leftover
# run >= min_shift_len is still proposed as a SHORT block (default min_shift_len=1).
for each unfilled block in the window, in date order:
    candidates = people available on all its days (A/AS/AR/- ok; no 'X')
                 AND past their minimum rest (>= 2 rotations since last shift)
    for each candidate:
        score =  w_total    * (how far below fair-share of total shifts, YTD)
               + w_weekend  * (how far below fair-share of weekends, YTD + current quarter*)
               + w_spacing  * (days since their last shift)        # maximize rest
               - w_question * (number of '?' days in this block)
        # fair-share target is FTE-weighted: total * fte_person / sum(fte),
        # not a flat total / n_people (equal FTE reduces to the equal split).
    if no candidate: leave block unfilled and FLAG it (never violate rest)
    else: assign highest-scoring candidate (stable tie-break)
    update tallies (shift-days, weekend-days by calendar quarter, last-shift date)

# *current-quarter counters are SEEDED from the prior quarter (carry-over), not reset to zero.
```

Greedy is chosen over an ILP optimizer for v1: simple, explainable, tunable. Every assignment
carries a `Rationale` (per-term score breakdown) so the reviewer sees *why* each pick was made.

## v1 decisions (locked) -> config values

All policy lives in `Settings` (config.py), not scattered in code:

| Decision | Settings field |
| --- | --- |
| `A/AS/AR/-` all "available" | `available_codes = {A, AS, AR, -}` |
| `?` penalized but eligible | `w_question` |
| 4-day blocks float freely (no weekday anchor) | `block_align = "float"` |
| Short shifts allowed (cover leftover runs < shift_len) | `min_shift_len = 1` |
| Fairness over YTD **and** calendar quarter | `quarter_mode = "calendar"` |
| Fair share FTE-weighted (equal-split fallback) | `fte_tab_name` (None ⇒ equal split) |
| Quarter seeded from prior quarter (not reset cold) | `quarter_seed = "carry_deviation"` |
| Minimum rest = 2 rotations (hard) + maximize spacing (soft) | `min_rest_rotations = 2`, `w_spacing` |
| Review-first output, never live rows | `output_target = "proposed_column"` |
| Proposal written to a SupSci-shaped duplicate tab | `proposal_tab_name`, `proposal_token = "S"` |
| No-shift dates skipped via the `Requires support?` row | `LayoutConfig.support_label` |

**Goal of the scoring:** minimize the spread (variance) of per-person load across scientists.

**One knob still open:** `quarter_seed` default is `"carry_deviation"` (carry each person's
prior-quarter deviation-from-mean into the new quarter). Alternatives: `"carry_total"`,
`"zero"`. Tune once there are real numbers; it's a one-line change in `tallies.py`.

## Suggested build order

1. `models.py` + `config.py` — domain types and the `Settings` dataclass. No logic yet.
2. `engine/tallies.py` — the two-horizon counter with quarter carry-over and last-shift
   tracking. **Most logic, fully pure -> write this with unit tests first** (hand-built fixtures,
   no Sheets).
3. `engine/blocks.py`, `eligibility.py`, `scoring.py`, then `greedy.py` — also pure, also
   testable with fixtures.
4. `io/parser.py` (grid -> domain model, with fixture grids), then `io/sheets.py` (real gspread).
5. `output/proposal.py`, then `output/writeback.py` (proposed column / CSV).
6. `cli.py` to wire it together. Run end-to-end against the real sheet last.

## Testing

- The whole `engine/` is pure — test it with small hand-built `AvailabilityGrid` + assignment
  fixtures. No OAuth, no network.
- Assert **determinism**: same inputs -> identical proposal (stable tie-break: lowest YTD load,
  then name).
- Cover the edge cases explicitly: a block with no eligible candidate (must be flagged, not
  filled), the rest rule across a person's prior assignment, and quarter-boundary carry-over.

## Conventions / guardrails

- **Never** let `engine/` import `gspread` or touch the filesystem. Adapters only at `io/` / `output/`.
- **Never** write into the live assignment rows. Writeback targets a CSV or a **separate
  SupSci-shaped duplicate tab** (`proposal_tab_name`); `io/sheets.write_proposal_calendar`
  hard-refuses to write the tab named by `tab_name` (the live `SupSci`).
- **Never** violate the minimum-rest rule — if it leaves no candidate, flag the block unfilled.
- **Never** commit the spreadsheet id, OAuth secrets, or tokens — load from env/config.
- Every `Assignment` in a `Proposal` carries its `Rationale`.
- Keep `Settings` the single home for tunable policy (weights + the decision flags above).
