# Algorithm

A transparent **greedy + scoring** heuristic is used for v1 — it is simple to implement, easy to
explain, and easy to tune. A full constraint optimizer (ILP via PuLP/OR-Tools) is a possible later
upgrade if results need to be more globally optimal.

The rules referenced below are defined in [Rules & Objectives](rules-and-objectives.md); the
modules that implement this loop are described in [Architecture](architecture.md).

## The loop (greedy + scoring)

```text
for each unfilled 4-day block in the window, in date order:
    candidates = people available on all 4 days (A/AS/AR/- ok; no 'X')
                 AND past their minimum rest (>= 2 rotations since last shift)
    for each candidate:
        score =  w_total    * (how far below fair-share of total shifts, YTD)
               + w_weekend  * (how far below fair-share of weekends, YTD + current quarter*)
               + w_spacing  * (days since their last shift)          # maximize rest between shifts
               - w_question * (number of '?' days in this block)
        # fair-share target is FTE-weighted: total * fte_person / sum(fte), not total / N
    if no candidate: leave the block unfilled and flag it for review
    else: assign the highest-scoring candidate (stable tie-break)
    update running tallies (shift-days, weekend-days by calendar quarter, last-shift date)

    # *current-quarter counters are seeded from the prior quarter (carry-over policy),
    #  not reset to zero, so balance carries across quarter boundaries.
```

Weights `w_*` are tunable knobs. Weekend days (Sat/Sun) are counted per block and rolled into the
per-person tallies that drive the next decision.

## Blocks and short shifts

Runs of consecutive unfilled days are chopped into `shift_len` (4-day) blocks, floating freely from
each gap with no weekday anchor. No-shift dates (the `Requires support?` row) break the runs.

A leftover run shorter than `shift_len` is **proposed as a short block** rather than dropped, so
short gaps still get covered — down to `min_shift_len` (default `1` = cover a single night; set it
to `shift_len` to require full blocks only).

## Why determinism and a score trace

Determinism matters for a tool whose output gets reviewed by a human: the greedy pick uses a
**stable tie-break** (lowest YTD load, then name), and the same inputs always yield the same
proposal.

Because the output is a *proposal for review*, each assignment carries a `Rationale` — the per-term
score breakdown that produced it. The reviewer can see *why* person P got block B (e.g. "furthest
below weekend fair-share, longest rested"), which is the whole advantage of greedy + scoring over an
opaque optimizer in v1.
