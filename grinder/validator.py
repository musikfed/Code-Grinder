"""Explicit validation states; the stage-1 default never runs generated code."""

from __future__ import annotations

import ast
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
    """Stage-1 syntax validation: Python AST; other languages need later adapters."""

    def validate(self, file_path: Path, content: str) -> ValidationResult:
        """Check a proposed in-memory file without executing or importing it."""
        suffix = file_path.suffix.lower()
        if suffix != ".py":
            return ValidationResult(
                Status.SKIPPED,
                f"Syntax checker not installed for {suffix or 'unknown language'}",
            )
        try:
            ast.parse(content, filename=str(file_path))
        except SyntaxError as exc:
            return ValidationResult(Status.FAIL, f"{exc.msg} at line {exc.lineno}")
        except Exception as exc:
            return ValidationResult(Status.ERROR, f"Python AST validator failed: {exc}")
        return ValidationResult(Status.PASS, "Python syntax OK (ast.parse; not executed)")
