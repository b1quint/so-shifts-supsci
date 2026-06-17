# Documentation

Design and decision docs for the **Shift Calendar Proposal Generator**, migrated from the
project's internal Confluence space so they live next to the code. These pages are the
source of truth for design and decisions — when the implementation diverges, update the
relevant page here (and the short status page on Confluence) rather than letting them drift.

The tool reads the SupSci availability spreadsheet and produces a **proposed** shift calendar
for review. It does **not** run the live schedule — it fills currently-empty dates and a human
reviews the proposal before it becomes real. See the top-level [CLAUDE.md](../CLAUDE.md) for the
build conventions and [HANDOFF.md](../HANDOFF.md) for build progress.

## Contents

| Page | What's in it |
| --- | --- |
| [Overview](overview.md) | Scope of v1, and why the tool is built in Python. |
| [Requirements & Data Model](requirements-and-data-model.md) | Availability codes, roles, constraints, and the draft backend data model. |
| [Rules & Objectives](rules-and-objectives.md) | Hard/soft scheduling rules and the fairness objectives. |
| [Algorithm](algorithm.md) | The greedy + scoring heuristic, with the loop sketch. |
| [Architecture](architecture.md) | Pure core behind an I/O boundary; module layout, data flow, decision → config map. |
| [FTE-Weighted Fair Share](fte-weighting.md) | Per-person target FTE and how it weights fair share. |
| [Sheet Integration](sheet-integration.md) | Sheet-reading details, proposal-tab writeback, and no-shift periods. |
| [Decisions (v1)](decisions.md) | The locked v1 decisions and how the run window is specified. |
| [Status](status.md) | Current status and planned enhancements. |

## Where things live

- **Code & build conventions:** [CLAUDE.md](../CLAUDE.md)
- **Build progress / handoff log:** [HANDOFF.md](../HANDOFF.md)
- **Repo:** [shift_calendar_proposal_generator](https://github.com/b1quint/shift_calendar_proposal_generator)
- **Confluence:** a single short [status page](https://rubinobs.atlassian.net/wiki/spaces/~60024d0e332c3a01075cd858/pages/1789231127)
  remains as a pointer back to these docs.
