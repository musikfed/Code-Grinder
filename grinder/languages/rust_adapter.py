"""Rust syntax-check via rustfmt; cargo checks require explicit trust."""

from __future__ import annotations

from pathlib import Path

from grinder.languages.base import BaseEnvAdapter
from grinder.validator import Status, ValidationResult


class RustAdapter(BaseEnvAdapter):
    """Avoid running arbitrary procedural macros during syntax-only checks."""

    name = "rust"
    extensions = (".rs",)

    def init_environment(self, project_dir: Path) -> ValidationResult:
        """Declare a minimal Cargo manifest without executing cargo."""
        manifest = project_dir / "Cargo.toml"
        if not manifest.exists():
            manifest.write_text(
                f'[package]\nname = "{project_dir.name.lower()}"\n'
                'version = "0.1.0"\nedition = "2021"\n', encoding="utf-8",
            )
        return (ValidationResult(Status.PASS, "Cargo.toml ready")
                if self.tool("cargo") else self.missing("cargo"))

    def sync_dependencies(self, project_dir: Path) -> ValidationResult:
        """Use cargo fetch only after trust is explicitly granted."""
        if not self.allow_build:
            return ValidationResult(Status.SKIPPED, "cargo fetch requires allow_build")
        cargo = self.tool("cargo")
        return (self.run([cargo, "fetch"], cwd=project_dir, timeout=120)
                if cargo else self.missing("cargo"))

    def validate(self, file_path: Path, content: str) -> ValidationResult:
        """rustfmt parses without build scripts; cargo check can run executable macros."""
        if rustfmt := self.tool("rustfmt"):
            return self.run([rustfmt, "--emit", "stdout"], source=content)
        return self.missing("rustfmt")
