"""Parse explicit multi-file AI answers; never interpret generated code as commands."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath


class Mode(StrEnum):
    """Supported change semantics."""

    CREATE = "CREATE"
    OVERWRITE = "OVERWRITE"
    APPEND = "APPEND"
    PATCH = "PATCH"


@dataclass(frozen=True)
class Change:
    """A proposed change; actual paths are validated again at write time."""

    target: str
    mode: Mode
    content: str
    expected_hash: str | None = None


class ParseError(ValueError):
    """Missing markers, unsafe path, or malformed model response."""


# MODE may share the TARGET line, or appear below it.
_TARGET = re.compile(
    r"^[ \t]*TARGET[ \t]*:[ \t]*(.+?)(?:[ \t]+MODE[ \t]*:[ \t]*"
    r"(CREATE|OVERWRITE|APPEND|PATCH))?[ \t]*$", re.IGNORECASE,
)
_MODE = re.compile(r"^[ \t]*MODE[ \t]*:[ \t]*(CREATE|OVERWRITE|APPEND|PATCH)[ \t]*$", re.IGNORECASE)
_HASH = re.compile(
    r"^[ \t]*(?:EXPECTED_SHA256|SHA256|HASH)[ \t]*:[ \t]*([0-9a-fA-F]{64})[ \t]*$",
    re.IGNORECASE,
)
_BAD_HASH = re.compile(r"^[ \t]*(?:EXPECTED_SHA256|SHA256|HASH)[ \t]*:", re.IGNORECASE)
_FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})([^\r\n]*)$")
_DRIVE = re.compile(r"^[A-Za-z]:")
_PROTECTED = {".git", ".grinder", ".grinder_tmp", ".venv", "__pycache__"}


def validate_target(target: str) -> str:
    """Normalize a relative POSIX-style path, forbidding traversal and internals."""
    if not isinstance(target, str):
        raise ParseError("TARGET must be a string")
    value = target.strip()
    if (not value or "\x00" in value or "\\" in value or value.startswith(("/", "~"))
            or _DRIVE.match(value) or ":" in value or "//" in value):
        raise ParseError(f"Unsafe TARGET: {target!r}")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ParseError(f"Unsafe TARGET: {target!r}")
    if any(part.casefold() in _PROTECTED for part in parts):
        raise ParseError(f"Reserved TARGET: {target!r}")
    if not PurePosixPath(value).parts:
        raise ParseError(f"Unsafe TARGET: {target!r}")
    return value


def parse_response(text: str) -> list[Change]:
    """Read fenced TARGET/MODE blocks; reject any incomplete batch in its entirety."""
    if not isinstance(text, str) or not text.strip():
        raise ParseError("Empty AI answer")
    changes: list[Change] = []
    target: str | None = None
    mode: Mode | None = None
    expected_hash: str | None = None
    collecting = False
    fence_char = ""
    fence_len = 0
    body: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines(keepends=True):
        raw = line.rstrip("\r\n")
        fence = _FENCE.match(raw)
        if collecting:
            if (fence and fence.group(1)[0] == fence_char
                    and len(fence.group(1)) >= fence_len and not fence.group(2).strip()):
                assert target is not None and mode is not None
                changes.append(Change(target, mode, "".join(body), expected_hash))
                target, mode, expected_hash = None, None, None
                collecting = False
                body = []
            else:
                body.append(line)
            continue
        match = _TARGET.match(raw)
        if match:
            if target is not None:
                raise ParseError("Incomplete TARGET before next TARGET")
            target = validate_target(match.group(1))
            if target.casefold() in seen:
                raise ParseError(f"Duplicate TARGET: {target}")
            seen.add(target.casefold())
            if match.group(2):
                mode = Mode(match.group(2).upper())
            continue
        match = _MODE.match(raw)
        if match:
            if target is None or mode is not None:
                raise ParseError("Unexpected MODE marker")
            mode = Mode(match.group(1).upper())
            continue
        match = _HASH.match(raw)
        if match:
            if target is None or expected_hash is not None:
                raise ParseError("Unexpected EXPECTED_SHA256 marker")
            expected_hash = match.group(1).lower()
            continue
        if target is not None and _BAD_HASH.match(raw):
            raise ParseError("Malformed EXPECTED_SHA256 marker")
        if fence and target is not None:
            if mode is None:
                raise ParseError(f"TARGET {target} has no MODE")
            collecting = True
            fence_char = fence.group(1)[0]
            fence_len = len(fence.group(1))
            body = []
    if collecting or target is not None:
        raise ParseError("Unterminated or incomplete TARGET block")
    if not changes:
        raise ParseError("No TARGET/MODE/code blocks found")
    return changes
