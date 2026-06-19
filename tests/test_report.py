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


def test_window_weeks_counts_inclusively():
    # Mon 2026-01-05 .. Sun 2026-01-11 = 7 days = exactly one week.
    assert window_weeks(date(2026, 1, 5), date(2026, 1, 11)) == 1.0
    assert window_weeks(date(2026, 1, 5), date(2026, 1, 18)) == 2.0


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
    # One full week window -> 40 working hours. Ann works 2 shift-days = 24 h.
    existing = {ANN: [date(2026, 1, 5), date(2026, 1, 6)]}
    rows = build_report(
        PEOPLE, existing, start=date(2026, 1, 5), end=date(2026, 1, 11), settings=SETTINGS
    )
    ann = {r.person: r for r in rows}["Ann"]
    assert ann.shift_hours == pytest.approx(24.0)
    assert ann.working_hours == pytest.approx(40.0)
    assert ann.shift_fraction == pytest.approx(24.0 / 40.0)


def test_fraction_independent_of_fte_uses_fulltime_denominator():
    # The report does not normalise by FTE: the denominator is always full-time.
    rows = build_report(
        PEOPLE, {}, start=date(2026, 1, 5), end=date(2026, 1, 11), settings=SETTINGS
    )
    assert all(r.working_hours == pytest.approx(40.0) for r in rows)


def test_hours_per_shift_is_configurable():
    existing = {ANN: [date(2026, 1, 5)]}
    s10 = Settings(hours_per_shift=10.0)
    rows = build_report(
        PEOPLE, existing, start=date(2026, 1, 5), end=date(2026, 1, 11), settings=s10
    )
    assert {r.person: r.shift_hours for r in rows}["Ann"] == pytest.approx(10.0)


def test_rows_sorted_by_most_shifts_then_name_deterministic():
    existing = {ANN: [date(2026, 1, 5)], BO: [date(2026, 1, 5), date(2026, 1, 6)]}
    rows = build_report(
        PEOPLE, existing, start=date(2026, 1, 1), end=date(2026, 1, 31), settings=SETTINGS
    )
    # Bo (2) first, then Ann (1), then Cai (0). Ann before Cai is name tie-break at 0? No: Ann=1.
    assert [r.person for r in rows] == ["Bo", "Ann", "Cai"]


def test_csv_rows_have_header_and_per_person_rows():
    existing = {ANN: [date(2026, 1, 5)]}
    rows = build_report(
        PEOPLE, existing, start=date(2026, 1, 5), end=date(2026, 1, 11), settings=SETTINGS
    )
    csv_rows = to_csv_rows(rows)
    assert csv_rows[0] == [
        "person",
        "shift_days",
        "weekend_days",
        "shift_hours",
        "working_hours",
        "shift_fraction",
    ]
    assert len(csv_rows) == 1 + len(PEOPLE)


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
