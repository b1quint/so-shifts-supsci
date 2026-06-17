# Handoff / build progress

Building the Shift Calendar Proposal Generator (see [CLAUDE.md](CLAUDE.md)) from scratch,
following its suggested build order.

- **Branch:** `mvp-v1` (pushed, tracks `origin/mvp-v1`)
- **Package manager:** `uv` (installed via Homebrew)
- **Run tests:** `uv run pytest -q`
- **Lint / format:** `uv run ruff check .` / `uv run ruff format .`

## Done (committed on `mvp-v1`)

- **Step 1 — scaffold:** flat `shift_proposer/` package, `models.py` (pure domain types),
  `config.py` (`Settings` + `from_env` for `SHIFT_SHEET_ID`), `.gitignore` for secrets, uv tooling.
- **Step 2 — `engine/tallies.py`:** two-horizon fairness counters. Stores assigned dates per
  person; derives YTD + calendar-quarter by filtering. `total_deficit` / `weekend_deficit`
  (positive = below fair share). Quarter seeded via `carry_deviation` (one-line switch to
  `carry_total` / `zero`).
- **Step 3a — `engine/blocks.py`:** `enumerate_blocks(dates, filled, shift_len)` → full
  `shift_len`-day blocks over consecutive unfilled calendar days, date order. Short tails dropped.
- **Step 3b — `engine/eligibility.py`:** hard candidate gate. `is_available_for_block` (reject any
  `X`; `?` stays eligible), `is_rested_for_block` (`min_rest_rotations * shift_len` days since last
  shift; never-assigned ⇒ rested), `is_eligible`, `eligible_people` (grid-ordered pool). "Skip
  filled" is handled upstream by `blocks.py`.
- **Step 3c — `engine/scoring.py`:** `score(grid, tallies, settings, person, block) -> (float,
  Rationale)`. Weighted sum: `+w_total*total_deficit +w_weekend*weekend_deficit
  +w_spacing*days_since_last -w_question*n_question`. `Rationale.terms` hold the *weighted*
  contributions (sum to total). Never-assigned ⇒ spacing term `0` (tunable choice).
- **Step 3d — `engine/greedy.py`:** `propose(grid, settings, existing=None) -> Proposal`. Seeds
  tallies + filled dates from `existing`, enumerates blocks, per block: eligible → score → pick
  highest (stable tie-break: lowest YTD load, then name) → record. Empty pool ⇒ block flagged
  unfilled. **The pure engine (step 3) is complete.**
- **Step 4a — `io/parser.py`:** raw cell grid → `AvailabilityGrid` + existing assignments
  (`dict[Person, list[date]]`). Encodes the real SupSci layout in a configurable `LayoutConfig`
  (names col A from row 6, calendar col D from row 2, 2 rows/person). `A/AS/AR/-` collapse via
  `Code.parse`; `?`/`X` preserved; assignments read from each person's shift row. `parse_date_row`
  resolves ISO or Sheets serials; bare day-of-month rejected as ambiguous (pass `dates=` to
  override).
- **Step 4b — `io/sheets.py`:** gspread + OAuth adapter (the ONLY gspread import). Fetches
  `UNFORMATTED_VALUE` (dates → serials), stringifies cells. `read_raw_grid` validates `sheet_id`
  before authorizing (fail fast). `load_sheet` = read + parse. Wiring tested with fakes; live
  `authorize()` untested.
- **Step 5a — `output/proposal.py`:** pure render layer. `to_rows` (chronological `ProposalRow`,
  unfilled merged inline) + `render_report` (text, score trace inline, unfilled flagged) +
  `term_columns`.
- **Step 5b — `output/writeback.py`:** CSV export (`to_csv_rows` pure, `write_csv` writes). Columns
  match the report (base + stable term columns); 4-dp numbers; never live rows. Proposed-column
  path deferred to first live run.
- **Step 6 — `cli.py`:** `Settings.from_env → load_sheet → select_window → propose → render_report
  + write_csv`. `[project.scripts]` entrypoint `shift-proposer`. Flags: `--csv`, `--sheet-id`,
  `--tab`, `--window-start/-end`. Pipeline tested through a fake sheet; only `main()` touches OAuth.

**84 tests passing, ruff clean. All six build steps complete — MVP is functionally done.**

## Decisions locked this build (beyond CLAUDE.md)

- Count unit = **shift-days**.
- Fair share = **equal split** (`total / N`).
- `quarter_seed` = **carry_deviation**.
- blocks: short remainders (< `shift_len`) **silently dropped** — OK'd for review; revisit if
  remainders should be *flagged* instead.

## First live run — DONE (2026-06-16)

Ran end-to-end against the real sheet (`SHIFT_SHEET_ID` + cached OAuth). Confirmed:

- **Date encoding resolved:** row-1 cells are true Google Sheets **serials** (via
  `UNFORMATTED_VALUE`), parsed correctly — no day-of-month ambiguity. `date_row=1` is right.
- **Roster gate fix:** sentinel/divider rows (`Science Support`, `(keep these rows empty)`) carry a
  name in col A and a populated shift row, so they were parsed as phantom people that marked every
  future date filled → empty proposal. Fixed by gating person rows on the `Avail` label in column C
  (`LayoutConfig.label_col` / `avail_label`). Now 9 real people; e.g. Jul–Sep 2026 → 14 assignments.

## `Out` marker + first real proposal — DONE (2026-06-16)

- **Fairness sanity-check resolved.** The earlier skew was Brian Stalder — an occasional coverer not
  in the official rotation — dragging down the fair-share mean. Added an **`Out`** roster marker
  (column C): a person marked `Out` is kept in the sheet but excluded from scheduling AND the
  fairness average. Brian + Kevin Fanning are now `Out`; parser returns `ParsedSheet.inactive` and
  the CLI reports exclusions. (Commit `8d73509`.)
- **Target window decided:** calendar is filled through 2026-08-02; the open gap is 2026-08-03 →
  2027-01-31. First real proposal generated for **2026-08-03 → 2026-10-01** (extended one day so the
  Sep 28 tail forms a full block): **15 assignments, 0 unfilled**. Load spread tightened (range
  11→6, stdev 3.84→1.96); rest rule 100% respected (verified: all short gaps are pre-existing
  history, none tool-caused).

## Confluence design page — updated (source of truth)

`Shift Calendar Proposal Generator`, page id **1789231127**, Bruno's personal space on
`rubinobs.atlassian.net` (cloudId `34f7173f-c7ca-4a05-82c6-d7f88d2266ec`). Updated to **IMPLEMENTED
— MVP**: resolved date-range (CLI args) + quarter-seed, added the `Out`/roster rule and the
Sheets-serial date handling. Child page *Requirements & Data Model* = 1790214149 (not yet touched).
Reachable via the Atlassian MCP in interactive sessions (read/write Confluence + Jira).

## FTE-weighted fair share — DONE (2026-06-17)

Point 1 of the three follow-ups is built and committed on `mvp-v1` (112 tests, ruff clean):

- **`engine/tallies.py`** — fair-share target is now `total * fte_person / sum(fte)` instead of a
  flat `total / N`. A person with no FTE entry defaults to weight `1.0`, so omitting FTE reproduces
  the old equal split exactly; deficits still sum to zero; non-positive FTE rejected. `Tallies.empty`
  gained an `fte=` arg; `greedy.propose` gained an `fte=` arg. (Commit `1aedc91`.)
- **`io/fte.py`** (new pure adapter) — parses a two-column FTE tab (name + target FTE %) into
  `{Person: weight}`. `parse_fte_value` accepts `"50%"`, a bare percent (`50`→0.5), and the fraction
  a percent cell yields when fetched unformatted (`0.5`); always returns a 0-1 fraction. Layout in
  `FteLayout` (default: name col A, FTE col B, data from row 2). Names are the **join key** to the
  roster. (Commit `8937563`.)
- **`io/sheets.py`** — `read_fte_grid` / `load_fte`; `open_worksheet` now takes a tab name.
  **`config.py`** — `fte_tab_name` (None ⇒ equal split). **`cli.py`** — `--fte-tab` flag; warns on
  name-join gaps both ways (roster member with no FTE → defaults 1.0; FTE name matching no member).
- **Tests** — FTE math in `test_tallies.py`, parser in `test_fte.py`, adapter in `test_sheets.py`,
  and an end-to-end `test_cli.py` case where the FTE tab *flips* a pick an equal split would make
  the other way. Docs (CLAUDE.md, README) updated.

**Still open before a live FTE run:** confirm the real FTE tab's name + layout (built against the
default name-col-A / FTE-col-B / row-2; user said they'd describe it but specifics not yet given),
then run end-to-end with `--fte-tab`. Confluence page not yet updated for this feature.

## Next — remaining follow-ups (points 2 & 3 of 2026-06-16)

2. **Output to a dedicated tab.** Push the proposal into a **separate tab** the user will create
   (not a column in `SupSci`, not just CSV). Implements `output/writeback.py`'s `proposed_column`
   path against that tab; live `SupSci` rows still never touched.
3. **No-shift periods.** Rare windows where **no shift runs at all** (shutdowns/engineering). Need a
   way to **flag** them so the tool skips them — neither proposing nor flagging as "unfilled — no
   candidate" (intentionally empty ≠ wanted-a-person-but-found-none). Likely a marker row/range the
   parser reads and `engine/blocks.py` excludes from enumeration.

## Other follow-ups (lower priority)

- **Tune weights** in `Settings` against real numbers (e.g. slight Tiago overshoot); revisit
  whether short block remainders should be *flagged* rather than dropped.
- When scheduling October, start the window at **2026-10-02** (Oct 1 is taken by the last Sep block).

## Commits

- `8d73509` — output: 'Out' marker excludes non-rotation people (+ CLAUDE/README docs)
- `1f3351b` — fix parser: gate roster on the 'Avail' label (live-sheet phantom-row bug)
- `62ee494` — cli: wire Settings -> sheets -> engine -> output (step 6)
- `a07da3b` — output/writeback: CSV export of a Proposal
- `6c92911` — output/proposal: render Proposal as review report + rows
- `182e2a4` — io/sheets: gspread+OAuth adapter -> raw SupSci grid
- `46e4256` — io/parser: raw SupSci grid -> AvailabilityGrid + existing assignments
- `c892529` — engine/greedy: date-ordered greedy fill into a Proposal
- `c2a5b2d` — engine/scoring: weighted candidate score with per-term rationale
- `c323e79` — engine/eligibility: hard candidate gate (X-block + min rest)
- `a7ba08f` — engine/blocks: enumerate unfilled shift-length blocks
- `fbb90ad` — engine/tallies: two-horizon fairness counters
- `eaa911f` — scaffold: domain models, Settings, uv tooling
