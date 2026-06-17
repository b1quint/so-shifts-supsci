# Requirements & Data Model (draft)

Working notes that translate the current spreadsheet workflow into requirements for the
[rso_shift_scheduler](https://github.com/b1quint/rso_shift_scheduler) application. This is a
**draft** bridge document, not a final spec — refine as the data model settles.

## What the spreadsheet does today

The Unified Summit Shifts Schedule answers one core question: *"Do we have all the roles needed for
a given day/night properly filled?"* It contains several per-role "shift sheets" plus a single
**Schedule Summary** that aggregates coverage. Dates are columns; each person occupies two rows.

### Availability codes (row 1 per person)

| Code | Meaning |
| --- | --- |
| `A` | Available to cover their shift |
| `AS` | Available to take a shift at the summit |
| `AR` | Available for remote support only |
| `X` | Not available |
| `?` | Unsure / only if no other option |
| `-` | Has not answered yet |

Row 2 per person holds the assigned shift/role code, if any. Each shift sheet carries its own
legend of codes in the top-left corner.

### Roles and shift lengths (from the Quarterly Shift Report)

| Role | Location | Shift length |
| --- | --- | --- |
| Camera Shift | Summit / Remote | 12 h |
| Commissioning Scientist Shift | Summit / Remote | 12 h |
| Day Remote | Remote | 10 h |
| Night Planner | Remote | 8 h |

Summit Tailgate attendance is also tracked. People based in La Serena are highlighted as those who
can usually take summit shifts.

## Constraints to encode

- **Coverage:** every required role must be filled for each operational day/night.
- **Summit vs remote:** respect each person's `AS`/`AR` availability; some roles are summit-only.
- **Safety:** a minimum of two staff at the summit at all times (day, night, weekends, holidays) —
  per the Lessons Learned paper.
- **Chilean labor law:** shift duration/rest rules, per the Provisional OS Shift Structure.
- **Equity & sustainability:** distribute load fairly; avoid fatigue/burnout; weekday vs weekend
  templates differ.

## Application: planned scope

From the repo README (features are *planned*, project is in initial setup):

- Staff availability management
- Shift assignment with conflict detection
- Calendar view of shifts
- Role-based access control
- Notifications for shift changes
- Schedule export (PDF, CSV)

**Stack:** Backend — Django 5.x, Django REST Framework, PostgreSQL, JWT auth. Frontend — React
18+, Vite, React Router, Axios, Material-UI or Tailwind.

## Proposed starting data model (draft)

A first cut that maps the spreadsheet onto the backend. Treat as a discussion starting point.

| Entity | Purpose / key fields |
| --- | --- |
| `Person` | Staff member: name, initials, home base (La Serena?), summit-eligible flag, role group. |
| `Role` | Camera, Commissioning Scientist, Day Remote, Night Planner, etc.; default length and location. |
| `Availability` | Person × date × code (`A/AS/AR/X/?/-`). The spreadsheet's row 1. |
| `Assignment` | Person × date × role × location. The spreadsheet's row 2. |
| `CoverageRequirement` | Per role, per day/night: how many people needed (drives the Summary check). |
| `CoverageStatus` | Derived: for each day/night, are all requirements met? (the question the Summary sheet answers.) |
