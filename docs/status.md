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

**Shift-utilization report** (`--report`) — a read-only summary of the shifts *already* on the sheet:
per person, total shift-days, weekend shift-days, and the fraction of full-time working hours spent
on shifts (**12 h/shift** over a `weeks × 40 h` full-time denominator, where weeks count every
calendar day in the range inclusively — `(end − start + 1) / 7`, no rounding). This is one day more
than the `Stats - SupSci` tab's `end − start` span, so the fraction sits a touch below the tab's
`Used Fraction of Time` by design — we count every day worked). Rows follow spreadsheet order by default;
`--sort fte` ranks by target FTE (with `--fte-tab`, which also adds an FTE column). Pure engine
(`engine/report.py`) + renderer (`output/report.py`); never writes. See the README's
[Reporting existing shifts](../README.md#reporting-existing-shifts).

Repo: [shift_calendar_proposal_generator](https://github.com/b1quint/shift_calendar_proposal_generator)
(branch `mvp-v1`). Build progress is tracked in [HANDOFF.md](../HANDOFF.md).

## Planned enhancements (next)

Remaining work, lower priority:

- **Tune the scoring weights** against real numbers (e.g. a slight Tiago overshoot); revisit whether
  short-block remainders should be *flagged* rather than covered.
- Optionally add a **clear/rewrite mode** for the proposal tab. The writeback is fill-empty-only by
  design, so re-running a window whose markers changed (e.g. an edited no-shift period) can leave
  stale cells; a clear/rewrite option would make re-runs clean.
