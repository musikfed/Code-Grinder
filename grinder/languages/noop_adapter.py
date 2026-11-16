"""No-op checker for arbitrary text, SQL, Bash, HTML and CSS."""

from __future__ import annotations

from pathlib import Path

from grinder.languages.base import BaseEnvAdapter
from grinder.validator import Status, ValidationResult


class NoOpAdapter(BaseEnvAdapter):
    """Explicitly SKIPPED: an unknown language is never considered valid."""

    name = "noop"
    extensions = (".sh", ".sql", ".html", ".htm", ".css")

    def init_environment(self, project_dir: Path) -> ValidationResult:
        """No environment is required for plain text."""
        return ValidationResult(Status.SKIPPED, "No environment for this stack")

    def sync_dependencies(self, project_dir: Path) -> ValidationResult:
        """No dependency resolver."""
        return ValidationResult(Status.SKIPPED, "No dependencies to synchronize")

    def validate(self, file_path: Path, content: str) -> ValidationResult:
        """Do not claim any syntax check happened."""
        return ValidationResult(Status.SKIPPED, f"No syntax checker for {file_path.suffix}")
