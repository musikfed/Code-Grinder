"""Strict SEARCH/REPLACE patch behavior."""

import pytest

from grinder.patches import PatchError, apply_patch


def test_exact_one_unique_search():
    """Apply the exact match without fuzzy or unexpected replacements."""
    old = "def f():\n    return 1\n"
    patch = "<<<<<<< SEARCH\n    return 1\n=======\n    return 2\n>>>>>>> REPLACE\n"
    assert apply_patch(old, patch) == "def f():\n    return 2\n"


@pytest.mark.parametrize("before", ["hello\nhello\n", "world\n"])
def test_reject_zero_or_multiple_matches(before):
    """A missing or ambiguous SEARCH block must never write."""
    patch = "<<<<<<< SEARCH\nhello\n=======\nbye\n>>>>>>> REPLACE\n"
    with pytest.raises(PatchError, match="exactly once"):
        apply_patch(before, patch)


def test_reject_empty_search_and_trailing_junk():
    """Never use empty SEARCH as a position-independent insertion."""
    with pytest.raises(PatchError):
        apply_patch("x\n", "<<<<<<< SEARCH\n=======\ny\n>>>>>>> REPLACE")
    with pytest.raises(PatchError):
        apply_patch("x\n", "<<<<<<< SEARCH\nx\n=======\ny\n>>>>>>> REPLACE\nOTHER")
