# Algorithm

A transparent **greedy + scoring** heuristic is used for v1 — it is simple to implement, easy to
explain, and easy to tune. A full constraint optimizer (ILP via PuLP/OR-Tools) is a possible later
upgrade if results need to be more globally optimal.

The rules referenced below are defined in [Rules & Objectives](rules-and-objectives.md); the
modules that implement this loop are described in [Architecture](architecture.md).

## The loop (greedy + scoring)

```text
for each unfilled 7-day block in the window, in date order (block always starts Monday):
    candidates = people available on all 7 days (A/AS/AR/- ok; no 'X')
                 AND past their minimum rest (>= 2 rotations since last shift)
    for each candidate:
        score =  w_total    * (how far below fair-share of total shifts, YTD)
               + w_spacing  * (days since their last shift)          # maximize rest between shifts
               - w_question * (number of '?' days in this block)
               - w_prep     * (number of unavailable days in the pre-shift prep window)
        # fair-share target is FTE-weighted: total * fte_person / sum(fte), not total / N
        # prep window = the Wed/Thu/Fri immediately before the block's Monday start;
        # not a hard blocker, just a soft nudge towards someone who can prepare
    if no candidate: leave the block unfilled and flag it for review
    else: assign the highest-scoring candidate (stable tie-break)
    update running tallies (shift-days YTD, last-shift date)
```

Weights `w_*` are tunable knobs.

With 7-day shifts every block spans exactly one weekend, so there is no separate
weekend-fairness term (and no calendar-quarter horizon) any more — total-shift fair share already
covers it. This also removes the old "two weekends in a row" concern entirely: it can't happen when
each rotation is a full week.

## Blocks and short shifts

Runs of consecutive unfilled days are chopped into `shift_len` (7-day) blocks, anchored to Monday: a
run is split at its first Monday into a leading short block (if the run starts mid-week) plus
Monday-Sunday full blocks from there on. No-shift dates (the `Requires support?` row) break the runs.

A leftover run shorter than `shift_len` is **proposed as a short block** rather than dropped, so
short gaps still get covered — down to `min_shift_len` (default `1` = cover a single night; set it
to `shift_len` to require full blocks only).

## Why determinism and a score trace

Determinism matters for a tool whose output gets reviewed by a human: the greedy pick uses a
**stable tie-break** (lowest YTD load, then name), and the same inputs always yield the same
proposal.

Because the output is a *proposal for review*, each assignment carries a `Rationale` — the per-term
score breakdown that produced it. The reviewer can see *why* person P got block B (e.g. "furthest
below fair-share, longest rested, fully prepped"), which is the whole advantage of greedy + scoring
over an opaque optimizer in v1.
