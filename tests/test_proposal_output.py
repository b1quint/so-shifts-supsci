"""Step-5 tests for output/proposal — rendering a Proposal for review.

Pure: hand-built Proposal objects, no I/O. We assert the flattened rows are
chronological with correct statuses, that the per-term breakdown survives, and
that the text report carries the score trace and flags unfilled blocks.
"""

from datetime import date, timedelta

from shift_proposer.models import Assignment, Block, Person, Proposal, Rationale
from shift_proposer.output.proposal import (
    STATUS_PROPOSED,
    STATUS_UNFILLED,
    render_report,
    to_rows,
)

ANN = Person("Ann")
MON = date(2026, 6, 1)


def block(start: date, n: int = 4) -> Block:
    return Block(dates=tuple(start + timedelta(days=i) for i in range(n)))


def assignment(person: Person, start: date) -> Assignment:
    rationale = Rationale(
        total=3.42,
        terms={"total": 2.67, "weekend": 0.5, "spacing": 0.0, "question": -0.5},
    )
    return Assignment(person=person, block=block(start), rationale=rationale)


def test_empty_proposal_renders_header_only():
    report = render_report(Proposal())
    assert report == "Proposed shift calendar — 0 assigned, 0 unfilled"
    assert to_rows(Proposal()) == []


def test_rows_are_chronological_and_merge_unfilled_inline():
    # Assignment in week 1, an unfilled gap in week 2, assignment in week 3.
    a1 = assignment(ANN, MON)
    a3 = assignment(ANN, MON + timedelta(days=14))
    gap = block(MON + timedelta(days=7))
    proposal = Proposal(assignments=(a1, a3), unfilled=(gap,))

    rows = to_rows(proposal)
    assert [r.start for r in rows] == [MON, MON + timedelta(days=7), MON + timedelta(days=14)]
    assert [r.status for r in rows] == [STATUS_PROPOSED, STATUS_UNFILLED, STATUS_PROPOSED]


def test_proposed_row_carries_person_score_and_terms():
    proposal = Proposal(assignments=(assignment(ANN, MON),))
    (row,) = to_rows(proposal)
    assert row.person == "Ann"
    assert row.score == 3.42
    assert row.terms["weekend"] == 0.5


def test_unfilled_row_has_no_person_or_score():
    proposal = Proposal(unfilled=(block(MON),))
    (row,) = to_rows(proposal)
    assert row.status == STATUS_UNFILLED
    assert row.person == ""
    assert row.score is None
    assert row.terms == {}


def test_report_shows_score_trace_in_preferred_term_order():
    proposal = Proposal(assignments=(assignment(ANN, MON),))
    report = render_report(proposal)
    line = report.splitlines()[1]
    assert "Ann" in line
    assert "score=+3.42" in line
    # terms appear in the preferred order, signed and 2-dp.
    assert "[total=+2.67 weekend=+0.50 spacing=+0.00 question=-0.50]" in line


def test_report_flags_unfilled_blocks():
    proposal = Proposal(unfilled=(block(MON),))
    report = render_report(proposal)
    assert "1 unfilled" in report.splitlines()[0]
    assert "⚠ UNFILLED" in report.splitlines()[1]
