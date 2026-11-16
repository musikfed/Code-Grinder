"""Standard unified diff preview for approval before any write."""

from __future__ import annotations

from difflib import unified_diff


def unified_change(before: str, after: str, target: str) -> str:
    """Return a standard unified diff (+ and - lines, with @@ hunks)."""
    return "".join(unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile=f"a/{target}", tofile=f"b/{target}", lineterm="\n",
    ))
