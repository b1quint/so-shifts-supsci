"""Step-3 tests for engine/blocks — enumerating unfilled shift-length blocks.

Pure: hand-built date ranges + a set of already-filled dates. Blocks float
freely (no weekday anchor); only full shift_len runs of *consecutive calendar
days* become blocks, in date order. A short tail (< shift_len) forms no block.
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


def test_short_tail_forms_no_block():
    window = days(MON, 5)  # one full block + a 1-day remainder
    blocks = enumerate_blocks(window, filled=set(), shift_len=4)
    assert len(blocks) == 1
    assert blocks[0].dates == tuple(window[0:4])
    # the trailing day is intentionally left uncovered
    assert window[4] not in {d for b in blocks for d in b.dates}


def test_run_shorter_than_shift_len_yields_no_blocks():
    blocks = enumerate_blocks(days(MON, 3), filled=set(), shift_len=4)
    assert blocks == []


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
