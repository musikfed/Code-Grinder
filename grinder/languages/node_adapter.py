"""JavaScript and TypeScript adapters with download-free validation."""

from __future__ import annotations

import json
from pathlib import Path

from grinder.languages.base import BaseEnvAdapter
from grinder.validator import Status, ValidationResult


class NodeAdapter(BaseEnvAdapter):
    """Prefer bun then pnpm then npm for explicit dependency synchronization."""

    name = "node"
    extensions = (".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx")

    def manager(self) -> tuple[str, str] | None:
        """Select the first locally available supported package manager."""
        for key in ("bun", "pnpm", "npm"):
            if executable := self.tool(key):
                return key, executable
        return None

    def init_environment(self, project_dir: Path) -> ValidationResult:
        """Create a minimal package.json without running package-manager scripts."""
        manifest = project_dir / "package.json"
        if not manifest.exists():
            manifest.write_text(
                json.dumps({"name": project_dir.name.lower(), "version": "0.1.0",
                            "private": True}, indent=2) + "\n", encoding="utf-8",
            )
        return (ValidationResult(Status.PASS, "package.json ready")
                if self.manager() else self.missing("bun / pnpm / npm"))

    def sync_dependencies(self, project_dir: Path) -> ValidationResult:
        """Install packages only on trusted explicit opt-in, never via the checker."""
        if not self.allow_build:
            return ValidationResult(Status.SKIPPED, "Install requires allow_build")
        choice = self.manager()
        if not choice:
            return self.missing("bun / pnpm / npm")
        name, executable = choice
        if name == "bun":
            command = [executable, "install", "--ignore-scripts"]
        elif name == "pnpm":
            command = [executable, "install", "--ignore-scripts"]
        else:
            command = [executable, "install", "--ignore-scripts"]
        return self.run(command, cwd=project_dir, timeout=120)

    def validate(self, file_path: Path, content: str) -> ValidationResult:
        """Use node --check on stdin; TypeScript requires a trusted checker."""
        if file_path.suffix.lower() in {".ts", ".tsx", ".jsx"}:
            return ValidationResult(
                Status.SKIPPED,
                "TSX/JSX/TypeScript checking requires trusted project tooling (tsc)",
            )
        node = self.tool("node")
        if not node:
            return self.missing("node")
        return self.run([node, "--check", "-"], source=content)
