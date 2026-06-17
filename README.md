# Shift Calendar Proposal Generator

Reads the **SupSci** availability spreadsheet and produces a **proposed** shift
calendar for a human to review. It only fills currently-empty dates and explains
*why* it picked each person — it does **not** edit your live schedule. You stay
in control: review the proposal, then apply whatever you agree with.

It's a sub-tool of the Unified Scheduling Tool project. For the full design and
the reasoning behind each decision, see [CLAUDE.md](CLAUDE.md).

---

## What it does

For every empty 4-day block in the window you choose, it picks the best-available
scientist using a simple, explainable scoring rule:

- **Fairness** — favors people who are below their fair share of total shifts and
  of weekend shifts (measured over the year and the calendar quarter). Fair share is
  **FTE-weighted** when a target-FTE tab is supplied (`--fte-tab`): a 50%-FTE person
  targets about half the shifts of a 100% one. Without it, fair share is an equal split.
- **Rest** — never schedules anyone with less than 2 rotations of rest since their
  last shift, and otherwise prefers whoever has rested longest.
- **Preferences** — treats a `?` (tentative) day as a small penalty.

If no one is eligible for a block, it leaves that block **unfilled and flagged**
rather than forcing a bad assignment. Every pick comes with a score breakdown so
you can see the rationale.

The result is printed as a readable report and written to a **CSV** you can open
in any spreadsheet. Optionally (`--out-tab`) it also fills the proposal into a
SupSci-shaped **duplicate tab** — a `"S"` in each assigned person's shift row,
empty cells only — so you can copy it across. The live source tab is never touched.

---

## Requirements

- **Python 3.11 or newer**
- **[uv](https://docs.astral.sh/uv/)** — the package/environment manager this
  project uses. Install it once:
  ```bash
  # macOS (Homebrew)
  brew install uv
  # or, any platform
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- A **Google account** that can open the spreadsheet, plus a one-time Google
  Cloud OAuth setup (below). You sign in as yourself — there is no service
  account and nothing to share.

---

## Install

Clone the repo and let `uv` create the environment and install dependencies:

```bash
git clone https://github.com/b1quint/shift_calendar_proposal_generator.git
cd shift_calendar_proposal_generator
uv sync
```

That's it — `uv` reads `pyproject.toml` and sets everything up. You'll run the
tool with `uv run …`, which uses this environment automatically.

---

## One-time Google authorization

The tool reads your spreadsheet through the Google Sheets API using **your own**
Google login. You authorize it once in a browser; after that a token is cached and
you won't be asked again. Setup takes about five minutes:

1. **Open the [Google Cloud Console](https://console.cloud.google.com/)** and
   create a project (or pick an existing one).
2. **Enable two APIs** for that project (APIs & Services → Library):
   - **Google Sheets API**
   - **Google Drive API**
3. **Configure the OAuth consent screen** (APIs & Services → OAuth consent
   screen): choose **External**, give it a name, and add **your own email as a
   test user**. You don't need to publish or get it verified — test mode is fine
   for personal use.
4. **Create credentials** (APIs & Services → Credentials → Create credentials →
   **OAuth client ID**): choose application type **Desktop app**. Download the
   resulting JSON file.
5. **Save that file** where the tool expects it:
   ```
   ~/.config/gspread/credentials.json
   ```
   (Create the `~/.config/gspread/` folder if it doesn't exist.)

The first time you run the tool it will open a browser asking you to sign in and
grant access. Approve it once; gspread then writes a cached token to
`~/.config/gspread/authorized_user.json` and reuses it on later runs.

> **Keep these files private.** `credentials.json` and the cached token are
> secrets — never commit them. This repo's `.gitignore` already excludes them.

---

## Find your spreadsheet id

Open the spreadsheet in your browser and copy the id from the URL — it's the long
string between `/d/` and `/edit`:

```
https://docs.google.com/spreadsheets/d/<THIS_IS_THE_ID>/edit#gid=0
```

You'll pass it via the `SHIFT_SHEET_ID` environment variable (recommended) or the
`--sheet-id` flag. **Don't commit the id** — keep it in your shell or a local
untracked `.env`.

---

## Run it

Set your spreadsheet id and run, choosing the date window you want proposals for:

```bash
SHIFT_SHEET_ID=<your-spreadsheet-id> \
  uv run shift-proposer --window-start 2026-07-01 --window-end 2026-09-30
```

This prints a review report and writes `proposal.csv` in the current folder.

To also FTE-weight fair share and fill a duplicate tab (preview first with
`--dry-run`, then drop it to write):

```bash
SHIFT_SHEET_ID=<your-spreadsheet-id> \
  uv run shift-proposer --window-start 2026-08-03 --window-end 2026-09-30 \
    --fte-tab "Stats - SupSci" --out-tab "SupSci Shift Proposal" --dry-run
```

### Options

| Flag | Default | Meaning |
| --- | --- | --- |
| `--window-start YYYY-MM-DD` | none | Earliest date to propose. |
| `--window-end YYYY-MM-DD` | none | Latest date to propose. |
| `--csv PATH` | `proposal.csv` | Where to write the CSV. |
| `--sheet-id ID` | `$SHIFT_SHEET_ID` | Spreadsheet id (overrides the env var). |
| `--tab NAME` | `SupSci` | Worksheet/tab to read. |
| `--fte-tab NAME` | none | Tab of per-person target FTE %; enables FTE-weighted fair share. |
| `--out-tab NAME` | none | SupSci-shaped duplicate tab to write the proposed calendar into (fills empty shift cells). |
| `--dry-run` | off | With `--out-tab`, report how many cells *would* be written without writing. |

If you omit the window, the whole calendar in the sheet is considered.

### What you get

A report like this on screen…

```
Proposed shift calendar — 12 assigned, 1 unfilled
2026-07-01 → 2026-07-04  Ann  score=+3.42  [total=+2.67 weekend=+0.50 spacing=+0.00 question=-0.50]
2026-07-05 → 2026-07-08  ⚠ UNFILLED — no eligible candidate
...
```

…and a `proposal.csv` with one row per block: status, dates, the proposed person,
the total score, and each score term in its own column — so you can sort, filter,
and double-check the reasoning in a spreadsheet.

---

## How the spreadsheet must be laid out

The tool reads the **SupSci** tab and expects this structure (the same layout the
team already uses):

- **Dates run across the columns**, starting at **column D**. The date for each
  column is in **row 2**.
- **Each person occupies two rows**, starting at **row 6**:
  - the **availability** row (top) — one code per date, and
  - the **shift** row (below) — the assigned shift/role for that date, if any.
- **Column A** holds the person's name (merged across their two rows);
  **column B** their initials; **column C** the per-row `Avail`/`Shift` label.
- Rows 1, 3, 4, 5 (month header, weekday, availability count, daily summary) are
  ignored.

**Column C is the roster gate.** A real rotation member's availability row says
`Avail` in column C. To keep someone in the sheet but **take them out of the
rotation** — e.g. someone who occasionally covers but isn't an official member —
change their column C from `Avail` to **`Out`**. They'll never be scheduled and
won't count toward anyone's fair share; the tool prints who it excluded. (This is
the right way to handle a non-rotation person — do **not** fill their row with
`X`, which would still count them in the fairness average.)

If your sheet differs, the positions live in one place — `LayoutConfig` in
[shift_proposer/io/parser.py](shift_proposer/io/parser.py) — and can be adjusted.

**No-shift periods.** A checkbox row labelled **`Requires support?`** (one box per
date) marks nights when no shift should run at all (shutdowns, engineering). Untick
it (**`FALSE`**) and the tool skips that date entirely — it is never proposed and
never flagged as "unfilled". Ticked or missing means a shift is wanted, so you can't
accidentally drop a date. The tool prints how many no-shift dates fell in your window.

### Target-FTE tab (optional)

To weight fair share by each person's dedication, point the tool at a tab holding
each member's **name** and **target FTE**, with `--fte-tab NAME` (for this workbook:
`--fte-tab "Stats - SupSci"`). Default layout matches that tab: **name in column A,
`Target Fraction of Time` in column I, people from row 6** to the first blank row.
Write the FTE as a percent (`100%`, `50%`). Names must match the SupSci tab exactly —
that's the join key, and the tool warns about any name it can't match (anyone missing
simply defaults to 100%; people marked `Out` are not flagged). Positions are
configurable in `FteLayout` in [shift_proposer/io/fte.py](shift_proposer/io/fte.py).
Without `--fte-tab`, fair share is a plain equal split.

### Availability codes

| Code | Meaning | Effect |
| --- | --- | --- |
| `A`, `AS`, `AR` | available (summit / remote) | eligible |
| `-` or blank | not answered | assumed available, eligible |
| `?` | tentative | eligible, with a small penalty |
| `X` | unavailable | hard block — never scheduled that day |

---

## Tuning the policy

All knobs live in one place: the `Settings` dataclass in
[shift_proposer/config.py](shift_proposer/config.py). Defaults:

- `shift_len = 4` (days per block), `min_rest_rotations = 2` (hard rest rule)
- weights: `w_total = 1.0`, `w_weekend = 1.0`, `w_spacing = 0.1`, `w_question = 0.5`
- `quarter_seed = "carry_deviation"` (how the quarterly weekend fairness carries
  over from the previous quarter)
- `fte_tab_name = None` (set via `--fte-tab` to weight fair share by target FTE)

These are starting points — tune them once you've seen real proposals.

---

## Limitations (this version)

- **Live rows untouched.** It writes a CSV and, with `--out-tab`, a separate
  SupSci-shaped duplicate tab. It never modifies the live `SupSci` assignment rows.
- **SupSci tab** (plus the optional FTE tab), run manually.
- The date encoding in row 2 is read as a real date. If your sheet stores only a
  bare day-of-month there, the tool will stop with a clear "ambiguous date" error
  — open an issue or adjust the parser to supply the year.

---

## For developers

The scheduling logic is a **pure core** (`shift_proposer/engine/`) with no Google
or filesystem dependencies, behind thin I/O adapters — so it's fully unit-tested
without any network or auth.

```bash
uv run pytest -q          # run the test suite
uv run ruff check .       # lint
uv run ruff format .      # format
```

See [CLAUDE.md](CLAUDE.md) for the architecture, the algorithm, and the locked v1
decisions.
