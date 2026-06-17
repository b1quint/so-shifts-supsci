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

Repo: [shift_calendar_proposal_generator](https://github.com/b1quint/shift_calendar_proposal_generator)
(branch `mvp-v1`). Build progress is tracked in [HANDOFF.md](../HANDOFF.md).

## Planned enhancements (next)

Remaining work, lower priority:

- **Tune the scoring weights** against real numbers (e.g. a slight Tiago overshoot); revisit whether
  short-block remainders should be *flagged* rather than covered.
- Optionally add a **clear/rewrite mode** for the proposal tab. The writeback is fill-empty-only by
  design, so re-running a window whose markers changed (e.g. an edited no-shift period) can leave
  stale cells; a clear/rewrite option would make re-runs clean.
