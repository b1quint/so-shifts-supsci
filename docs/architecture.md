# Architecture

**Guiding principle — a pure core behind an I/O boundary.** The scheduling logic (`engine/`)
imports nothing from `gspread` or the filesystem: it takes plain domain objects in and returns a
`Proposal` out. Google Sheets is just one *adapter* at the edge. This is what makes the algorithm
reusable in the future Django backend — swap the Sheets adapter for an ORM adapter and the engine is
unchanged.

## Package layout

```text
shift_proposer/
├── cli.py            # entrypoint: build Settings, wire adapter → engine → output
├── config.py         # Settings dataclass: weights, shift_len=4, window, policy values
├── models.py         # PURE domain types: Person, Code(enum), AvailabilityGrid, Block, Assignment, Proposal, Rationale
├── io/
│   ├── sheets.py     # gspread + OAuth: open SupSci + FTE tabs → raw cell grid  (the ONLY gspread import)
│   ├── parser.py     # raw grid → AvailabilityGrid + existing Assignments + no-shift dates; A/AS/AR/- → available
│   └── fte.py        # raw FTE tab → {Person: weight} (Target Fraction of Time, keyed by name)
├── engine/           # PURE. no gspread, no I/O. domain objects in, Proposal out.
│   ├── blocks.py     # enumerate unfilled blocks in the window, date order; blocks float freely; short tail >= min_shift_len
│   ├── eligibility.py# hard rules: skip filled, reject any 'X', enforce >=2-rotation rest
│   ├── tallies.py    # shift-days + weekend-days on 2 horizons (YTD + calendar quarter w/ carry-over); FTE-weighted fair share; last-shift date
│   ├── scoring.py    # score(person, block, tallies) → float + per-term breakdown (incl. spacing reward)
│   └── greedy.py     # main loop: block → eligible → score → pick best (stable tie-break) → update tallies
└── output/
    ├── proposal.py   # Proposal: list[Assignment] + per-pick Rationale (the score trace) for review
    └── writeback.py  # CSV export + plan_calendar_fill (pure) → CellUpdates for a duplicate tab — never live rows
```

## Responsibilities at a glance

| Layer | Module(s) | Responsibility | Knows about gspread? |
| --- | --- | --- | --- |
| Edge / adapter | `io/sheets.py` | OAuth + read the SupSci and FTE tabs as raw cells; apply the calendar writeback. | Yes (only here) |
| Translation | `io/parser.py`, `io/fte.py` | Raw grid ⇄ domain model; code normalization; no-shift dates; FTE tab → weights; layout index for writeback. | No |
| Core (pure) | `engine/*` | Blocks, eligibility, tallies, scoring, greedy loop. | No |
| Result | `output/proposal.py` | Carry assignments + score rationale for review. | No |
| Result → edge | `output/writeback.py` | Render proposal to CSV; plan the duplicate-tab cell fills (pure). | Via adapter |
| Wiring | `cli.py`, `config.py` | Settings + dependency wiring. | No |

## Data flow (one run)

1. **cli** builds a `Settings` object — sheet id, window, weights, policy values.
2. **io.sheets** authorizes via OAuth and pulls the whole `SupSci` tab as a raw cell grid (and the
   `Stats - SupSci` FTE tab when `--fte-tab` is set).
3. **io.parser** turns the grid into the domain model: an `AvailabilityGrid` (person × date → code)
   plus the set of existing `Assignment`s and the no-shift dates. It reads the **full year**, not
   just the window, because history seeds the tallies. Collapses `A/AS/AR/-` to "available".
   `io.fte` parses the FTE tab into per-person weights.
4. **engine.tallies** seeds per-person counters from the existing assignments — shift-days +
   weekend-days on both horizons (YTD, and the current calendar quarter carried over from the prior
   quarter), plus each person's last-shift date — and computes each person's FTE-weighted fair-share
   target.
5. **engine.blocks** lists the unfilled 4-day blocks inside the window, in date order, floating from
   each gap (no-shift dates break the runs).
6. **engine.greedy** walks the blocks: `eligibility` drops anyone with an `X` and anyone still
   inside their rest window; `scoring` ranks the rest; the top candidate (stable tie-break) is
   assigned; `tallies` updates so the next block sees fresh numbers. A block with no eligible
   candidate is left unfilled and flagged.
7. **output.proposal** accumulates each pick plus its score breakdown.
8. **output.writeback** renders the proposal to CSV and, when `--out-tab` is set, plans the cells to
   fill in the duplicate tab; `io.sheets` applies them. Live assignment rows are never modified.

Steps 4 and 6 are the heart of the loop; everything else is plumbing around a pure core.

## Decision → config map

Each resolved decision maps to one config value in one module, so policy stays in `Settings` rather
than scattered through the code. See [Decisions](decisions.md) for the rationale behind each.

| Decision (v1) | Settings field | Module |
| --- | --- | --- |
| `A/AS/AR/-` all "available" | `available_codes = {A, AS, AR, -}` | `io/parser.py` |
| `?` penalized (still eligible) | `w_question` | `engine/scoring.py` |
| Blocks float freely | `block_align = "float"` | `engine/blocks.py` |
| Short shifts allowed (cover leftover runs < shift_len) | `min_shift_len = 1` | `engine/blocks.py` |
| Calendar quarter, seeded from prior quarter | `quarter_mode = "calendar"`, `quarter_seed = "carry_deviation"` | `engine/tallies.py` |
| FTE-weighted fair share (equal-split fallback) | `fte_tab_name` (None ⇒ equal split) | `io/fte.py` + `engine/tallies.py` |
| Proposal written to a SupSci-shaped duplicate tab | `proposal_tab_name`, `proposal_token = "S"` | `output/writeback.py` + `io/sheets.py` |
| No-shift dates skipped (`Requires support?` = FALSE) | `LayoutConfig.support_label` | `io/parser.py` + `engine/greedy.py` |
| Minimum rest + maximize spacing | `min_rest_rotations = 2` (hard) + `w_spacing` (soft) | `engine/eligibility.py` + `scoring.py` |
| Review-first output | `output_target = "proposed_column"` | `output/writeback.py` |
| Roster gate + `Out` exclusion (column C) | `avail_label = "Avail"`, `inactive_label = "Out"` | `io/parser.py` (`LayoutConfig`) |
