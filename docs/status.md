# Status

**IMPLEMENTED — MVP** — built and run live against the `SupSci` tab (2026). The pure engine +
Sheets adapter (OAuth) + CSV output + CLI are all unit-tested; the first real proposal was generated
and validated against the live sheet (per-person load spread measurably tightened, rest rule fully
respected).

All three follow-ups from the original plan are implemented and run live:

- **FTE-weighted fair share** — see [FTE-Weighted Fair Share](fte-weighting.md).
- **Writeback into the `SupSci Shift Proposal` duplicate tab** — see
  [Sheet Integration](sheet-integration.md#writeback-to-the-proposal-tab).
- **No-shift periods** (the `Requires support?` row) — see
  [Sheet Integration](sheet-integration.md#no-shift-periods).

**Short shifts** (covering leftover runs shorter than a full block) are also implemented — see
[Algorithm](algorithm.md#blocks-and-short-shifts).

Also shipped since the initial MVP:

- **`--mode complete|rebuild`** — controls whether in-window existing shifts are kept (gaps only) or
  reopened for re-proposal.
- **`--clear`** — wipes shift assignments in the proposal tab's window (respects `--dry-run` and the
  window flags) so a window can be given a clean slate before `--mode rebuild`. This closes the
  stale-cell gap that used to be listed below as a planned "clear/rewrite mode".
- **`--apply`** — writes the proposal directly into the live `SupSci` tab, in addition to the CSV and
  duplicate-proposal-tab outputs.
- **Stronger `?` handling** — `w_question` raised to make tentative-availability days a true last
  resort via two-tier candidate selection, plus a `--w-question` CLI override.

**Shift-utilization report** (`--report`) — a read-only summary of the shifts *already* on the sheet:
per person, total shift-days, weekend shift-days, and the fraction of full-time working hours spent
on shifts (**12 h/shift** over a `weeks × 40 h` full-time denominator, where weeks count every
calendar day in the range inclusively — `(end − start + 1) / 7`, no rounding). This is one day more
than the `Stats - SupSci` tab's `end − start` span, so the fraction sits a touch below the tab's
`Used Fraction of Time` by design — we count every day worked). Rows follow spreadsheet order by default;
`--sort fte` ranks by target FTE (with `--fte-tab`, which also adds an FTE column). Pure engine
(`engine/report.py`) + renderer (`output/report.py`); never writes. See the README's
[Reporting existing shifts](../README.md#reporting-existing-shifts).

Repo: [so-shifts-supsci](https://github.com/b1quint/so-shifts-supsci)
(branch `mvp-v1`). Build progress is tracked in [HANDOFF.md](../HANDOFF.md).

## In progress

- **7-day Monday-anchored shifts + prep-window penalty** (branch `tickets/RSO-910`, ticket
  [RSO-921](https://rubinobs.atlassian.net/browse/RSO-921)) — replaces the 4-day floating-block model
  described above with 7-day blocks that always start on Monday, and adds a soft scoring penalty for
  being unavailable in the Wed/Thu/Fri right before the shift starts. Also removes weekend-specific
  fairness tracking (moot once every shift spans exactly one weekend) in favor of a single YTD
  horizon. See [Algorithm](algorithm.md), [Decisions](decisions.md), and
  [HANDOFF.md](../HANDOFF.md#7-day-monday-anchored-shifts--prep-window-penalty--in-progress-2026-09-04)
  for the details; not yet run against the live sheet.

## Planned enhancements (next)

Remaining work, lower priority:

- **Tune the scoring weights** against real numbers (e.g. a slight Tiago overshoot); revisit whether
  short-block remainders should be *flagged* rather than covered. Tracked in
  [RSO-912](https://rubinobs.atlassian.net/browse/RSO-912).
