# Overview

A sub-tool of the **Unified Scheduling Tool** project. It reads the existing availability
spreadsheet and produces a **proposed** shift calendar for review — it does not run the live
schedule. Availability codes referenced throughout are defined on the
[Requirements & Data Model](requirements-and-data-model.md) page.

## Scope (first version — deliberately small)

- **Runs manually** for now, in **local Python** (via the Google Sheets API). No
  scheduled/automated runs yet.
- **Summit Support Scientists only** — the `SupSci` tab. Mixing with other tabs/roles comes later.
- **Source of truth:** the *Unified Summit Shifts Schedule — 2026*, `SupSci` tab. Each person has
  an availability row and an assignment row; dates are columns. (The spreadsheet id is supplied via
  the `SHIFT_SHEET_ID` environment variable and never committed.)
- **Output:** a proposed set of assignments for currently-empty dates, for the user to review
  before it becomes the real schedule.

## Runtime — Python (decided)

**Decision:** build the tool in Python rather than Apps Script.

**Why:** the hard part is the assignment logic — greedy selection, candidate scoring, and tracking
per-person shift and weekend tallies across the whole year and a calendar quarter while minimizing
variance. That is data-shaped work that is fast to write and debug in Python (pandas / datetime)
and awkward in Apps Script's JavaScript. It also matches the existing
[rso_shift_scheduler](https://github.com/b1quint/rso_shift_scheduler) repo and the future Django
backend, so the logic written now is reusable rather than throwaway.

**Auth:** use `gspread` with OAuth user credentials — authorize once, the token is cached. No
service-account or sheet-sharing setup needed for a sheet the user already owns. This is the only
real setup cost (~15 minutes, one time).

**Distribution (later):** if non-Python colleagues eventually need a one-click run, the clean
pattern is a thin Apps Script menu button in the sheet that calls the deployed Python logic —
brains in Python, button in the sheet. Build only when distribution actually matters.
