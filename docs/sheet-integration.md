# Sheet Integration

How the tool reads the live `SupSci` tab, writes the proposal back, and handles no-shift nights.
Layout positions referenced here are all configurable in `parser.LayoutConfig` (and `fte.FteLayout`
for the FTE tab), so a sheet-layout change is a config tweak, not a code edit.

## Sheet-reading details (from the live sheet)

Learned while wiring the reader to the real `SupSci` tab:

- **Dates are Google Sheets serials.** The date row stores real date serials; the reader fetches
  with `UNFORMATTED_VALUE` and converts them, so there is no day-of-month ambiguity. (A bare
  day-of-month would be rejected as ambiguous rather than guessed.)
- **Column C is the roster gate.** `Avail` marks a real person's availability row (`Shift` the row
  below). This is what separates scientists from sentinel/divider rows (e.g. `Science Support`,
  `(keep these rows empty)`) that also carry text in column A — without it, such rows were being
  read as phantom people whose populated shift row marked every future date as filled. `Out`
  excludes a person from the rotation (see [Rules & Objectives](rules-and-objectives.md)).
- **Shift-cell token is `"S"`.** A person is on a summit-support shift when their shift row holds
  `"S"` under that date — identity comes from the row, not the token. (Camera shifts are tracked on
  a different tab, which is why a Camera-only coverer shows no `"S"` in SupSci.) The writeback
  replicates this exact convention.
- **FTE tab `Stats - SupSci`.** Target FTE per person lives in column I (`Target Fraction of Time`),
  names in column A from row 6 to the first blank row. Read unformatted, a 50% cell comes back as
  `0.5`. See [FTE-Weighted Fair Share](fte-weighting.md).
- **`Requires support?` checkbox row.** A per-date checkbox row (found by its column-A label) flags
  no-shift nights: a `FALSE` box marks a date the tool must skip. Checkboxes read as booleans; only
  an explicit `FALSE` counts, so a missing/ticked box never drops a date.

## Writeback to the proposal tab

**Implemented.** With `--out-tab` the proposal is written into a **SupSci-shaped duplicate tab**
(`SupSci Shift Proposal`), filled the way a human fills the original: a token (`"S"`) in each
assigned person's shift row, under each date of the block, **only into empty cells** (existing
assignments are never overwritten). A pure planner (`output/writeback.plan_calendar_fill`) decides
which cells to fill; `io/sheets.write_proposal_calendar` applies them in one batch and **hard-refuses
to write the live `SupSci` tab**. `--dry-run` reports the cell count without writing. First live
fill: the Q3 open gap (2026-08-03 → 2026-09-30), verified by read-back.

## No-shift periods

**Implemented.** A per-date checkbox row labelled `Requires support?` flags nights when *no shift
should run at all* (shutdowns / engineering): an unticked (`FALSE`) box marks a no-shift date. Those
dates are **excluded from block enumeration entirely** — neither proposed nor flagged "unfilled — no
candidate" (intentionally empty ≠ wanted-a-person-but-found-none) — and never seed the tallies. The
parser finds the row by its column-A label (robust to row moves); only an explicit `FALSE` counts,
so a missing or ticked box never silently drops a date. The CLI reports how many no-shift dates fell
in the window. (On the live sheet, 2026-08-17 → 2026-08-21 is currently marked no-shift.)
