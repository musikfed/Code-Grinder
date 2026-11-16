"""Common non-shell subprocess policy for optional language toolchains."""

from __future__ import annotations

import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

from grinder.validator import Status, ValidationResult


class BaseEnvAdapter(ABC):
    """Language-specific initialization and checking with explicit build opt-in."""

    name = "base"
    extensions: tuple[str, ...] = ()

    def __init__(self, *, allow_build: bool = False) -> None:
        """Default to syntax-only and no dependency installation."""
        self.allow_build = allow_build

    @staticmethod
    def tool(*options: str) -> str | None:
        """Return first installed executable or None, without invoking it."""
        return next((candidate for name in options if (candidate := shutil.which(name))), None)

    @staticmethod
    def run(
        args: list[str], *, cwd: Path | None = None, source: str | None = None,
        timeout: int = 20,
    ) -> ValidationResult:
        """Run an explicit trusted tool without a shell or implicit package downloads."""
        try:
            completed = subprocess.run(
                args, cwd=cwd, input=source, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout, check=False,
            )
            detail = (completed.stderr or completed.stdout or "Exit code 0").strip()[:3000]
            return ValidationResult(
                Status.PASS if completed.returncode == 0 else Status.FAIL, detail,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ValidationResult(Status.ERROR, f"Tool failed: {exc}")

    def missing(self, name: str) -> ValidationResult:
        """Explain why a checker cannot run instead of returning false PASS."""
        return ValidationResult(Status.SKIPPED, f"{name} is not installed")

    @abstractmethod
    def init_environment(self, project_dir: Path) -> ValidationResult:
        """Prepare language environment with no unsafe defaults."""

    @abstractmethod
    def sync_dependencies(self, project_dir: Path) -> ValidationResult:
        """Synchronize dependencies only with explicit allow_build=True."""

    @abstractmethod
    def validate(self, file_path: Path, content: str) -> ValidationResult:
        """Check proposed in-memory source; never silently execute that source."""
