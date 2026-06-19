# FTE-Weighted Fair Share

**Implemented.** Fair share is **FTE-weighted**: each person's target is
`total × fte_person / Σfte` instead of a flat `total / N`, so a 50%-FTE person targets about half
the shifts of a 100% one. A person with no FTE entry defaults to weight `1.0`, and with equal
weights the formula reduces exactly to the old equal split.

- **Where it lives:** a separate tab, the live `Stats - SupSci`. The adapter (`io/fte.py`) reads
  **name in column A** and `Target Fraction of Time` **in column I**, for people from **row 6** down
  to the first blank-name row.
- **Join key = name.** FTE rows are matched back to the roster by name, so a typo silently drops a
  weight — the CLI warns on mismatches in both directions (a roster member with no FTE entry, or an
  FTE name matching nobody), except for people already marked `Out`.
- **Enabled by** pointing `Settings.fte_tab_name` at the tab (CLI `--fte-tab "Stats - SupSci"`);
  when unset, fair share falls back to the equal split. Layout is configurable in `fte.FteLayout`.
- **Relative-only.** Fair share depends only on the *ratio* of targets, so the
  shift-hours-vs-FTE-hours conversion (a global constant) does not affect who is picked — it would
  only matter for an absolute expected-shift-count figure. The tool standardises on **12 h/shift**
  (`Settings.hours_per_shift`); this constant is only consulted for absolute figures such as the
  [shift-utilization report](status.md).
- **Currently inert:** every person's target is presently 50%, so the FTE-weighted proposal is
  byte-identical to the equal split (verified). It diverges as soon as targets differ.

Parsing accepts `"50%"`, a bare percent (`50` → `0.5`), and the fraction a percent cell yields when
fetched unformatted (`0.5`); it always returns a 0–1 fraction.
