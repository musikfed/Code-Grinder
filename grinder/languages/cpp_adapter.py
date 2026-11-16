"""C++ syntax-only checking via g++ or clang++ without compilation artifacts."""

from __future__ import annotations

from pathlib import Path

from grinder.languages.base import BaseEnvAdapter
from grinder.validator import Status, ValidationResult


class CppAdapter(BaseEnvAdapter):
    """A syntax-only C/C++ checker; external includes still require caution."""

    name = "cpp"
    extensions = (".cpp", ".cc", ".cxx", ".hpp", ".hh", ".h")

    def init_environment(self, project_dir: Path) -> ValidationResult:
        """Declare minimal CMake project without executing CMake scripts."""
        cmake = project_dir / "CMakeLists.txt"
        if not cmake.exists():
            cmake.write_text(
                "cmake_minimum_required(VERSION 3.18)\n"
                f"project({project_dir.name.replace('-', '_')} LANGUAGES CXX)\n"
                "add_executable(app main.cpp)\n", encoding="utf-8",
            )
        return (ValidationResult(Status.PASS, "CMakeLists.txt ready")
                if self.tool("g++", "clang++") else self.missing("g++ / clang++"))

    def sync_dependencies(self, project_dir: Path) -> ValidationResult:
        """Do not run configure/build automatically for untrusted CMakeLists.txt."""
        return ValidationResult(Status.SKIPPED, "CMake configure/build requires trusted workflow")

    def validate(self, file_path: Path, content: str) -> ValidationResult:
        """Check syntax using compiler stdin and -fsyntax-only."""
        compiler = self.tool("g++", "clang++")
        if not compiler:
            return self.missing("g++ / clang++")
        return self.run([compiler, "-fsyntax-only", "-x", "c++", "-"], source=content)
