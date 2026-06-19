"""Tests for the per-person shift-utilization report (engine + output).

Pure: hand-built people + assigned dates, no Sheets, no network. Covers the
window filtering, weekend counting, the 12 h/shift × full-time-40 h fraction,
determinism of the row order, and the CSV/text shaping.
"""

from datetime import date

import pytest

from shift_proposer.config import Settings
from shift_proposer.engine.report import build_report, window_weeks
from shift_proposer.models import Person
from shift_proposer.output.report import render_report, to_csv_rows

ANN = Person("Ann")
BO = Person("Bo")
CAI = Person("Cai")
PEOPLE = (ANN, BO, CAI)
SETTINGS = Settings()  # 12 h/shift, 40 h/week


def test_window_weeks_counts_every_day_inclusively():
    # Mon 2026-01-05 .. Sun 2026-01-11 = 7 days = exactly one week (both endpoints).
    assert window_weeks(date(2026, 1, 5), date(2026, 1, 11)) == 1.0
    assert window_weeks(date(2026, 1, 5), date(2026, 1, 18)) == 2.0
    # The Stats window 2026-04-01 .. 2026-06-30 spans 91 calendar days -> 13.0 weeks
    # (one more than the tab's 90-day span — we count every day in the range).
    assert window_weeks(date(2026, 4, 1), date(2026, 6, 30)) == pytest.approx(91 / 7)


def test_window_weeks_rejects_reversed_window():
    with pytest.raises(ValueError):
        window_weeks(date(2026, 1, 10), date(2026, 1, 1))


def test_counts_shift_and_weekend_days_in_window():
    existing = {
        # Thu, Fri, Sat, Sun -> 4 shift-days, 2 weekend.
        ANN: [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 4)],
        BO: [date(2026, 1, 5)],  # Mon -> 1 shift-day, 0 weekend.
    }
    rows = build_report(
        PEOPLE, existing, start=date(2026, 1, 1), end=date(2026, 1, 7), settings=SETTINGS
    )
    by_name = {r.person: r for r in rows}
    assert (by_name["Ann"].shift_days, by_name["Ann"].weekend_days) == (4, 2)
    assert (by_name["Bo"].shift_days, by_name["Bo"].weekend_days) == (1, 0)
    assert (by_name["Cai"].shift_days, by_name["Cai"].weekend_days) == (0, 0)


def test_dates_outside_window_are_excluded():
    existing = {ANN: [date(2025, 12, 31), date(2026, 1, 3), date(2026, 2, 1)]}
    rows = build_report(
        PEOPLE, existing, start=date(2026, 1, 1), end=date(2026, 1, 31), settings=SETTINGS
    )
    assert {r.person: r.shift_days for r in rows}["Ann"] == 1


def test_fraction_is_shift_hours_over_fulltime_hours():
    # Window 2026-01-05 .. 2026-01-11 -> 7 inclusive days -> 1.0 week -> 40 hours.
    # Ann works 2 shift-days = 24 h.
    existing = {ANN: [date(2026, 1, 5), date(2026, 1, 6)]}
    rows = build_report(
        PEOPLE, existing, start=date(2026, 1, 5), end=date(2026, 1, 11), settings=SETTINGS
    )
    ann = {r.person: r for r in rows}["Ann"]
    assert ann.shift_hours == pytest.approx(24.0)
    assert ann.working_hours == pytest.approx(40.0)  # 1.0 week * 40 h
    assert ann.shift_fraction == pytest.approx(24.0 / 40.0)


def test_fraction_independent_of_fte_uses_fulltime_denominator():
    # The report does not normalise by FTE: the denominator is always full-time.
    rows = build_report(
        PEOPLE, {}, start=date(2026, 1, 5), end=date(2026, 1, 11), settings=SETTINGS
    )
    assert all(r.working_hours == pytest.approx(40.0) for r in rows)


def test_hours_per_shift_is_configurable():
    # Default is 12 h/shift; override to an arbitrary value to prove the knob works.
    existing = {ANN: [date(2026, 1, 5)]}
    custom = Settings(hours_per_shift=6.0)
    rows = build_report(
        PEOPLE, existing, start=date(2026, 1, 5), end=date(2026, 1, 11), settings=custom
    )
    assert {r.person: r.shift_hours for r in rows}["Ann"] == pytest.approx(6.0)


def test_default_order_preserves_spreadsheet_order():
    # Bo works more shifts, but the default keeps the input (spreadsheet) order.
    existing = {ANN: [date(2026, 1, 5)], BO: [date(2026, 1, 5), date(2026, 1, 6)]}
    rows = build_report(
        PEOPLE, existing, start=date(2026, 1, 1), end=date(2026, 1, 31), settings=SETTINGS
    )
    assert [r.person for r in rows] == ["Ann", "Bo", "Cai"]


def test_sort_by_fte_ranks_highest_first_ties_keep_sheet_order():
    fte = {ANN: 0.5, BO: 1.0, CAI: 1.0}
    rows = build_report(
        PEOPLE,
        {},
        start=date(2026, 1, 1),
        end=date(2026, 1, 31),
        settings=SETTINGS,
        fte=fte,
        sort_by="fte",
    )
    # Bo & Cai (1.0) before Ann (0.5); the 1.0 tie keeps spreadsheet order (Bo, Cai).
    assert [r.person for r in rows] == ["Bo", "Cai", "Ann"]
    assert {r.person: r.fte for r in rows}["Ann"] == 0.5


def test_missing_fte_treated_as_fulltime_when_ranking():
    # Cai has no FTE entry -> treated as 1.0, so it outranks the explicit 0.5.
    fte = {ANN: 0.5, BO: 0.5}
    rows = build_report(
        PEOPLE,
        {},
        start=date(2026, 1, 1),
        end=date(2026, 1, 31),
        settings=SETTINGS,
        fte=fte,
        sort_by="fte",
    )
    assert rows[0].person == "Cai"
    assert rows[0].fte is None  # no entry -> recorded as None, ranked as 1.0


def test_fte_is_none_without_fte_map():
    rows = build_report(
        PEOPLE, {}, start=date(2026, 1, 1), end=date(2026, 1, 31), settings=SETTINGS
    )
    assert all(r.fte is None for r in rows)


def test_build_report_rejects_unknown_sort():
    with pytest.raises(ValueError):
        build_report(
            PEOPLE,
            {},
            start=date(2026, 1, 1),
            end=date(2026, 1, 31),
            settings=SETTINGS,
            sort_by="bogus",
        )


def test_csv_rows_have_header_and_per_person_rows():
    existing = {ANN: [date(2026, 1, 5)]}
    rows = build_report(
        PEOPLE, existing, start=date(2026, 1, 5), end=date(2026, 1, 11), settings=SETTINGS
    )
    csv_rows = to_csv_rows(rows)
    assert csv_rows[0] == [
        "person",
        "target_fte",
        "shift_days",
        "weekend_days",
        "shift_hours",
        "working_hours",
        "shift_fraction",
    ]
    assert len(csv_rows) == 1 + len(PEOPLE)
    # No FTE supplied -> the target_fte cell is blank.
    assert csv_rows[1][1] == ""


def test_csv_writes_target_fte_fraction_when_supplied():
    existing = {ANN: [date(2026, 1, 5)]}
    rows = build_report(
        PEOPLE,
        existing,
        start=date(2026, 1, 5),
        end=date(2026, 1, 11),
        settings=SETTINGS,
        fte={ANN: 0.5},
    )
    by_person = {row[0]: row for row in to_csv_rows(rows)[1:]}
    assert by_person["Ann"][1] == "0.5000"


def test_render_report_handles_empty_window():
    text = render_report([], start=date(2026, 1, 1), end=date(2026, 1, 7))
    assert "no assigned shifts" in text


def test_render_report_includes_total_footer():
    existing = {ANN: [date(2026, 1, 5), date(2026, 1, 6)], BO: [date(2026, 1, 7)]}
    rows = build_report(
        PEOPLE, existing, start=date(2026, 1, 5), end=date(2026, 1, 11), settings=SETTINGS
    )
    text = render_report(rows, start=date(2026, 1, 5), end=date(2026, 1, 11))
    assert "TOTAL" in text
    assert "Ann" in text and "Bo" in text
