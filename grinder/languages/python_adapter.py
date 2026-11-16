"""Python environment discovery and side-effect-free AST syntax checks."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from grinder.languages.base import BaseEnvAdapter
from grinder.validator import Status, ValidationResult


class PythonAdapter(BaseEnvAdapter):
    """Python via uv or venv; validation uses only the stdlib AST parser."""

    name = "python"
    extensions = (".py",)

    def init_environment(self, project_dir: Path) -> ValidationResult:
        """Initialize uv environment or a local venv only on explicit wizard request."""
        if (project_dir / ".venv").exists():
            return ValidationResult(Status.PASS, "Virtual environment already exists")
        if not self.allow_build:
            return ValidationResult(Status.SKIPPED, "Run with allow_build to create venv")
        if uv := self.tool("uv"):
            return self.run([uv, "venv", str(project_dir / ".venv")], cwd=project_dir)
        return self.run([sys.executable, "-m", "venv", str(project_dir / ".venv")])

    def sync_dependencies(self, project_dir: Path) -> ValidationResult:
        """Explicitly opt in to uv sync or pip requirements installation."""
        if not self.allow_build:
            return ValidationResult(Status.SKIPPED, "Dependency installation requires allow_build")
        if uv := self.tool("uv"):
            return self.run([uv, "sync"], cwd=project_dir, timeout=120)
        requirements = project_dir / "requirements.txt"
        if not requirements.exists():
            return ValidationResult(Status.SKIPPED, "No requirements.txt and uv unavailable")
        return self.run(
            [sys.executable, "-m", "pip", "install", "-r", str(requirements)],
            cwd=project_dir, timeout=120,
        )

    def validate(self, file_path: Path, content: str) -> ValidationResult:
        """Parse Python without imports, execution or __pycache__ writes."""
        try:
            ast.parse(content, filename=str(file_path))
        except SyntaxError as exc:
            return ValidationResult(Status.FAIL, f"{exc.msg} at line {exc.lineno}")
        except Exception as exc:
            return ValidationResult(Status.ERROR, f"AST checker error: {exc}")
        return ValidationResult(Status.PASS, "Python syntax OK (ast.parse)")
