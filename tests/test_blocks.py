"""Step-3 tests for engine/blocks — enumerating unfilled shift-length blocks.

Pure: hand-built date ranges + a set of already-filled dates. Blocks float
freely (no weekday anchor); runs of *consecutive calendar days* are chopped
into shift_len blocks, in date order, and a leftover >= min_shift_len is emitted
as a short block (min_shift_len defaults to 1, so short gaps are covered).
"""

from datetime import date, timedelta

from shift_proposer.engine.blocks import enumerate_blocks

MON = date(2026, 6, 1)  # arbitrary contiguous range anchor


def days(start: date, n: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


def test_no_dates_yields_no_blocks():
    assert enumerate_blocks([], filled=set(), shift_len=4) == []


def test_single_full_run_becomes_one_block():
    window = days(MON, 4)
    blocks = enumerate_blocks(window, filled=set(), shift_len=4)
    assert len(blocks) == 1
    assert blocks[0].dates == tuple(window)


def test_run_chops_into_consecutive_full_blocks():
    window = days(MON, 8)
    blocks = enumerate_blocks(window, filled=set(), shift_len=4)
    assert [b.dates for b in blocks] == [tuple(window[0:4]), tuple(window[4:8])]


def test_short_tail_becomes_a_short_block_by_default():
    window = days(MON, 6)  # one full block + a 2-day remainder
    blocks = enumerate_blocks(window, filled=set(), shift_len=4)
    assert [b.dates for b in blocks] == [tuple(window[0:4]), tuple(window[4:6])]


def test_run_shorter_than_shift_len_becomes_one_short_block():
    blocks = enumerate_blocks(days(MON, 3), filled=set(), shift_len=4)
    assert [b.dates for b in blocks] == [tuple(days(MON, 3))]


def test_min_shift_len_drops_tails_below_the_floor():
    window = days(MON, 6)  # 4-day block + a 2-day tail
    # With a floor of 3, the 2-day tail is too short and is dropped.
    blocks = enumerate_blocks(window, filled=set(), shift_len=4, min_shift_len=3)
    assert [b.dates for b in blocks] == [tuple(window[0:4])]


def test_min_shift_len_equal_to_shift_len_requires_full_blocks():
    window = days(MON, 5)  # full block + 1-day tail
    blocks = enumerate_blocks(window, filled=set(), shift_len=4, min_shift_len=4)
    assert [b.dates for b in blocks] == [tuple(window[0:4])]


def test_filled_date_splits_the_run():
    window = days(MON, 9)
    filled = {window[4]}  # the 5th day already has an assignment
    blocks = enumerate_blocks(window, filled=filled, shift_len=4)
    # run [0..3] -> block; day 4 filled; run [5..8] -> block
    assert [b.dates for b in blocks] == [tuple(window[0:4]), tuple(window[5:9])]
    assert window[4] not in {d for b in blocks for d in b.dates}


def test_calendar_gap_splits_the_run():
    # Omit one day from the window so dates are not contiguous.
    window = days(MON, 4) + days(MON + timedelta(days=5), 4)  # 4 + gap + 4
    blocks = enumerate_blocks(window, filled=set(), shift_len=4)
    assert len(blocks) == 2
    assert blocks[0].dates == tuple(window[0:4])
    assert blocks[1].dates == tuple(window[4:8])


def test_blocks_are_in_date_order_even_if_input_unsorted():
    window = days(MON, 8)
    shuffled = list(reversed(window))
    blocks = enumerate_blocks(shuffled, filled=set(), shift_len=4)
    starts = [b.start for b in blocks]
    assert starts == sorted(starts)


def test_shift_len_is_respected():
    window = days(MON, 6)
    blocks = enumerate_blocks(window, filled=set(), shift_len=2)
    assert [len(b.dates) for b in blocks] == [2, 2, 2]


def test_duplicate_dates_do_not_inflate_blocks():
    window = days(MON, 4) * 2  # same four days twice
    blocks = enumerate_blocks(window, filled=set(), shift_len=4)
    assert len(blocks) == 1


# --- anchor_weekday (7-day Monday-start shifts) -----------------------------

MONDAY = date(2026, 6, 1)  # a Monday


def test_anchor_weekday_none_preserves_float_behaviour():
    window = days(MONDAY + timedelta(days=2), 7)  # starts on a Wednesday
    blocks = enumerate_blocks(window, filled=set(), shift_len=7, anchor_weekday=None)
    assert [b.dates for b in blocks] == [tuple(window)]


def test_run_starting_on_the_anchor_weekday_needs_no_leading_block():
    window = days(MONDAY, 14)
    blocks = enumerate_blocks(window, filled=set(), shift_len=7, anchor_weekday=0)
    assert [b.dates for b in blocks] == [tuple(window[0:7]), tuple(window[7:14])]
    assert all(b.start.weekday() == 0 for b in blocks)


def test_run_not_starting_on_monday_gets_a_leading_short_block():
    # Run starts on Wednesday: a 5-day leading block (Wed-Sun) up to the first
    # Monday, then a full 7-day block anchored on it.
    window = days(MONDAY + timedelta(days=2), 12)  # Wed .. 12 days later
    blocks = enumerate_blocks(window, filled=set(), shift_len=7, anchor_weekday=0)
    assert [b.dates for b in blocks] == [tuple(window[0:5]), tuple(window[5:12])]
    assert blocks[1].start.weekday() == 0


def test_leading_partial_dropped_below_min_shift_len():
    # Run starts on Sunday: only 1 day before the first Monday.
    window = days(MONDAY - timedelta(days=1), 8)  # Sun + one full Mon-Sun week
    blocks = enumerate_blocks(
        window, filled=set(), shift_len=7, min_shift_len=2, anchor_weekday=0
    )
    # The 1-day Sunday lead is below the floor and dropped; only the full week remains.
    assert [b.dates for b in blocks] == [tuple(window[1:8])]


def test_run_entirely_before_the_anchor_weekday_becomes_one_short_block():
    window = days(MONDAY + timedelta(days=2), 3)  # Wed, Thu, Fri — no Monday in run
    blocks = enumerate_blocks(window, filled=set(), shift_len=7, anchor_weekday=0)
    assert [b.dates for b in blocks] == [tuple(window)]
