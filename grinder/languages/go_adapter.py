"""Go via go mod; syntax-only validation with gofmt stdin."""

from __future__ import annotations

from pathlib import Path

from grinder.languages.base import BaseEnvAdapter
from grinder.validator import Status, ValidationResult


class GoAdapter(BaseEnvAdapter):
    """Use gofmt for safe parsing, require opt-in for go mod tidy/build."""

    name = "go"
    extensions = (".go",)

    def init_environment(self, project_dir: Path) -> ValidationResult:
        """Write a minimal go.mod without running external module hooks."""
        manifest = project_dir / "go.mod"
        if not manifest.exists():
            manifest.write_text(f"module {project_dir.name.lower()}\n\ngo 1.22\n", encoding="utf-8")
        return (ValidationResult(Status.PASS, "go.mod ready")
                if self.tool("go") else self.missing("go"))

    def sync_dependencies(self, project_dir: Path) -> ValidationResult:
        """Run go mod tidy only when explicitly trusted."""
        if not self.allow_build:
            return ValidationResult(Status.SKIPPED, "go mod tidy requires allow_build")
        go = self.tool("go")
        return (self.run([go, "mod", "tidy"], cwd=project_dir, timeout=120)
                if go else self.missing("go"))

    def validate(self, file_path: Path, content: str) -> ValidationResult:
        """Parse gofmt stdin (no compilation or package execution)."""
        gofmt = self.tool("gofmt")
        return self.run([gofmt, "-e"], source=content) if gofmt else self.missing("gofmt")
