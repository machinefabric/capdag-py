"""The page-selection grammar, held to the reference's numbers (``src/pages.rs``).

Every assertion is on the indices, 0-based, in the order the parser emits them:
the order IS the answer — a spec that reorders pages is a spec somebody wrote
to reorder pages.
"""

import pytest

from capdag.pages import parse_index_range


def test_0060_index_range_grammar():
    """TEST0060: the full grammar — singles, ranges, open ranges, comma lists,
    written order preserved, duplicates dropped on first occurrence."""
    assert parse_index_range(None, 3) == [0, 1, 2]
    assert parse_index_range("", 3) == [0, 1, 2]
    assert parse_index_range("2", 5) == [1]
    assert parse_index_range("2-4", 5) == [1, 2, 3]
    assert parse_index_range("3-", 5) == [2, 3, 4]
    assert parse_index_range("1,3,5-7", 10) == [0, 2, 4, 5, 6]
    # Written order is preserved; a duplicate keeps its first occurrence.
    assert parse_index_range("5,1,3,1-2", 10) == [4, 0, 2, 1]


def test_0061_index_range_clamps_past_end():
    """TEST0061: an over-long range clamps to the document instead of erroring
    (the parser this replaced hard-errored on ``1-100`` of a 10-page document)."""
    assert parse_index_range("1-100", 10) == list(range(10))
    assert parse_index_range("8-100", 10) == [7, 8, 9]
    # A single page past the end is a start-past-end error, not a clamp (see
    # TEST0062) — clamping only widens a range that STARTS in bounds.


def test_0062_index_range_hard_errors():
    """TEST0062: genuinely impossible selections stay hard errors, with
    messages that name the numbers involved."""
    with pytest.raises(ValueError) as starts_past_end:
        parse_index_range("11-20", 10)
    assert "starts at page 11" in str(starts_past_end.value)
    assert "10 pages" in str(starts_past_end.value)

    # 0 is not a page.
    with pytest.raises(ValueError):
        parse_index_range("0-3", 10)
    # Backwards.
    with pytest.raises(ValueError):
        parse_index_range("5-2", 10)
    # Garbage.
    with pytest.raises(ValueError):
        parse_index_range("abc", 10)
    with pytest.raises(ValueError):
        parse_index_range("1,,3", 10)
    # Any selection at all from an empty document.
    with pytest.raises(ValueError):
        parse_index_range("1", 0)
