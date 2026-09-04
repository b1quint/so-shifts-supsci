# Rules & Objectives

The scheduling rules the engine enforces, and the fairness objectives the scoring serves.
Availability codes are defined on the [Requirements & Data Model](requirements-and-data-model.md)
page; how the rules map onto config lives in [Architecture](architecture.md).

## Rules

| Rule | Type | Behavior |
| --- | --- | --- |
| Default shift length = 7 days, Monday-anchored | Convention | New shifts are generated as 7-day blocks that always start on a Monday. A run not starting on a Monday gets a short leading block up to the first one. Other lengths only exist if entered manually beforehand. |
| Availability tiers (v1) | Convention | `A`, `AS`, `AR` and `-` are all treated as plain "available" — summit/remote is ignored for v1, and unanswered (`-`) is assumed available (the common case where a request for availability goes unanswered). `?` is available-but-penalized; `X` blocks. |
| Roster membership (column C) | Hard | A person's row is part of the rotation only if column C reads `Avail` (the row below reads `Shift`). This is also what separates real scientists from sentinel/divider rows that carry text in column A (e.g. `Science Support`, `(keep these rows empty)`). A row marked `Out` is kept in the sheet for records but **excluded entirely** — never scheduled and never counted in any fair-share average — which is the correct way to handle occasional coverers who are not official rotation members (do **not** mark them `X` everywhere, which would still count them in the headcount and distort everyone's fair share). The CLI reports who was excluded. |
| No-shift nights (`Requires support?`) | Hard | A date whose `Requires support?` checkbox is `FALSE` needs no shift at all (shutdown / engineering) and is skipped entirely — never proposed, never flagged unfilled. See [Sheet Integration](sheet-integration.md#no-shift-periods). |
| Don't overwrite existing assignments | Hard | Only dates with no shift assigned are filled. Manually-entered shifts (including non-7-day ones) are fixed anchors. |
| Respect the date range | Hard | Only dates within the user-specified window are touched (see [Decisions](decisions.md#date-range)). |
| Never assign on an `X` day | Hard | If a person marked `X` on *any* day of a candidate 7-day block, they are ineligible for that block. |
| Minimum rest between shifts | Hard | After working a block, a person is ineligible until at least **two further 7-day rotations** have passed (~14 clear days), so everyone gets time to rest. Rest is never traded away: if it leaves no eligible person, the block is left unfilled and flagged. |
| Avoid `?` days | Soft | People are still considered, but a block containing their `?` days is penalized in scoring — preferred only if no better option exists. |
| Prepare for the shift | Soft | The person on shift is expected to be available to prepare during the Wed/Thu/Fri immediately before their Monday start. Being unavailable (`X`) on those days is not a blocker, just a scoring penalty (graded by how many of the 3 days are affected) that favors someone who can actually prepare. |
| Maximize spacing | Soft | Beyond the hard rest floor, the scorer rewards candidates who have gone longest since their last shift, so everyone's shifts are spread as far apart as possible. |

## Balancing objectives

**Overarching goal:** keep shift load as **even as possible across scientists** — i.e. minimize the
spread (variance) of per-person load. The terms below all serve that single end.

- **Even distribution:** total shift load (shift-days or blocks) should be as even as possible
  across people, accounting for year-to-date totals so people who already carried more are favored
  less. Fair share is **FTE-weighted** (see [FTE-Weighted Fair Share](fte-weighting.md)): each
  person's target is proportional to their target fraction of time, not a flat `total / N`.
- **Spacing / rest:** beyond the hard minimum rest, spread each person's shifts as far apart in time
  as possible.
- **Prep readiness:** favor candidates who are actually available to prepare the week before their
  shift, without ever hard-blocking on it.

Weekend fairness was a separate objective under the old 4-day model, where shifts could land on
different weekdays and someone could end up working two weekends in a row. With 7-day Monday-anchored
shifts every block spans exactly one weekend, so weekend load is inseparable from total-shift load —
there is no longer a distinct weekend term, and the two-weekends-in-a-row scenario no longer exists.
Fairness is now tracked on a single horizon (year-to-date); the old calendar-quarter horizon and its
carry-over policy existed only to serve the removed weekend term.
