"""Strict, non-fuzzy SEARCH/REPLACE patches for weak LLM output."""

from __future__ import annotations

from dataclasses import dataclass


class PatchError(ValueError):
    """Reject ambiguous or malformed patches before modifying a file."""


@dataclass(frozen=True)
class SearchReplace:
    """An exact search fragment and its replacement."""

    search: str
    replace: str


def parse_patch(payload: str) -> SearchReplace:
    """Parse one exact PATCH block (no fuzzy matching or silent whitespace changes)."""
    opener = "<<<<<<< SEARCH\n"
    separator = "=======\n"
    legacy_separator = "======= REPLACE\n"
    ending = ">>>>>>> REPLACE"
    legacy_ending = ">>>>>>> END"
    if not payload.startswith(opener) or payload.count(opener) != 1:
        raise PatchError("PATCH must begin with exactly one <<<<<<< SEARCH line")
    middle = legacy_separator if legacy_separator in payload else separator
    if payload.count(middle) != 1:
        raise PatchError("PATCH requires exactly one ======= separator")
    search, tail = payload[len(opener):].split(middle, 1)
    terminator = ending if ending in tail else legacy_ending
    if tail.count(terminator) != 1:
        raise PatchError("PATCH requires exactly one >>>>>>> REPLACE terminator")
    replace, extra = tail.split(terminator, 1)
    if extra.strip():
        raise PatchError("Trailing PATCH text is not permitted")
    if not search:
        raise PatchError("SEARCH cannot be empty")
    return SearchReplace(search, replace)


def apply_patch(before: str, payload: str) -> str:
    """Apply only if the SEARCH fragment occurs exactly once."""
    part = parse_patch(payload)
    matches = before.count(part.search)
    if matches != 1:
        raise PatchError(f"SEARCH must match exactly once; found {matches}")
    return before.replace(part.search, part.replace, 1)
