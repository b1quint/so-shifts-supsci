# Decisions (v1)

Resolved — these are locked for the first version. Each maps to a config value in `Settings`; see
the [Architecture decision → config map](architecture.md#decision--config-map).

## Date range

How the user specifies the run window. Three options were considered:

| Option | How | Trade-off |
| --- | --- | --- |
| A. Config cells in the sheet | Dedicated "Generate from / Generate to" cells (the sheet already has a Start/End visible-date config block to model this on). | One source of truth; works identically for Apps Script and Python. |
| B. Script parameters | `--start` / `--end` args. | Flexible per-run, but not recorded anywhere; easy to forget what was used. |
| C. Implicit default | From the first unassigned date through a fixed horizon (e.g. end of visible range, or +N weeks). | Zero input, but least control. |

**Resolved (v1): Option B — script parameters.** The window is passed on the CLI as
`--window-start` / `--window-end` (ISO dates), and the spreadsheet id via the `SHIFT_SHEET_ID`
environment variable (never committed). Config cells in the sheet (Option A) remain the intended
later upgrade once the tool graduates from manual runs.

## Locked v1 decisions

- Treat `-` (not answered) as available (same tier as `A`) — unanswered availability requests are
  assumed available.
- Ignore the summit/remote distinction — `A`/`AS`/`AR` all count as "available" for v1.
- 4-day blocks float freely from the first gap; no weekday anchoring.
- A leftover run shorter than `shift_len` is covered as a **short shift** (`min_shift_len`, default
  `1`) rather than dropped.
- Fairness is tracked on two horizons: year-to-date and the current calendar quarter, with the
  quarter seeded (carried over) from the previous quarter so balance isn't reset cold.
- A person must rest at least two 4-day rotations before being reassigned; beyond that, maximize
  spacing. Rest is a hard guarantee — never traded away.
- If the rest rule leaves no eligible person for a block, leave it unfilled and flagged rather than
  forcing a violation.
- Write the proposal to a separate proposed copy/tab for review first — never straight into the live
  assignment rows. (v1 ships CSV and the in-sheet proposed tab.)
- The run window is specified by `--window-start` / `--window-end` CLI args (Option B), and the
  spreadsheet id via the `SHIFT_SHEET_ID` environment variable.
- Non-rotation people (occasional coverers) are marked `Out` in column C: kept in the sheet for
  records but excluded from scheduling and from the fair-share average. They are **not** marked `X`
  everywhere, which would still count them in the headcount.
- Quarter carry-over uses carry-deviation-from-mean (`quarter_seed = "carry_deviation"`): someone
  who was overloaded starts the new quarter already "ahead" on the tally. The alternatives (carry
  full totals, or hard-reset to zero) remain one-line switches in `engine/tallies.py`.
- Fair share is FTE-weighted by each person's Target Fraction of Time (read from the `Stats - SupSci`
  tab via `--fte-tab`); with no FTE tab, or equal targets, it reduces to the equal split.
- The proposal is written into a SupSci-shaped duplicate tab (`SupSci Shift Proposal`, via
  `--out-tab`) the way a human fills the original — a token (`"S"`) in each assigned person's shift
  row, under each date, empty cells only. The writer hard-refuses the live `SupSci` tab.
- No-shift nights (shutdowns/engineering) are flagged by a per-date `Requires support?` checkbox row:
  a `FALSE` box excludes that date from block enumeration — neither proposed nor flagged unfilled,
  and never seeds the tallies. Only an explicit `FALSE` counts.
