"""Explicit validation states; the stage-1 default never runs generated code."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class Status(StrEnum):
    """Only PASS means syntax was actually checked."""

    PASS = "PASS"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class ValidationResult:
    """Status with a human-readable reason."""

    status: Status
    detail: str


class Validator:
    """Dispatch syntax checks through language adapters; no implicit build execution."""

    def __init__(self, *, allow_build: bool = False) -> None:
        """Keep potentially executable build/check phases disabled by default."""
        self.allow_build = allow_build

    def validate(self, file_path: Path, content: str) -> ValidationResult:
        """Validate the proposed in-memory file through its registered adapter."""
        from grinder.languages import adapter_for_file

        return adapter_for_file(file_path, allow_build=self.allow_build).validate(
            file_path, content,
        )
