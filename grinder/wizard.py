"""Offline-safe project setup; prompts or explicit CLI arguments choose a stack."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from grinder.database import Database
from grinder.languages import ADAPTERS, get_adapter
from grinder.validator import ValidationResult

_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,62}$")
ARCHITECTURES = ("Minimal", "MVC", "Clean")


@dataclass(frozen=True)
class InitResult:
    """Created project path and environment discovery outcome."""

    path: Path
    adapter_status: ValidationResult


def create_project(
    parent: Path, name: str = "my_project", language: str = "python",
    architecture: str = "Minimal", *, allow_build: bool = False,
) -> InitResult:
    """Scaffold one new project without clobbering preexisting sources."""
    if not _NAME.fullmatch(name):
        raise ValueError("Project name must be a short ASCII identifier, no slashes or dots")
    key = language.strip().casefold()
    if key not in ADAPTERS:
        raise ValueError(f"Unsupported language: {language}")
    arch = architecture.strip().capitalize()
    if arch not in ARCHITECTURES:
        raise ValueError(f"Unknown architecture: {architecture}")
    directory = Path(parent).expanduser().resolve() / name
    if directory.is_symlink() or (hasattr(directory, "is_junction") and directory.is_junction()):
        raise ValueError("Refusing symlink/junction project folder")
    if directory.exists() and any(directory.iterdir()):
        raise FileExistsError(f"Project is not empty: {directory}")
    directory.mkdir(parents=True, exist_ok=True)

    # Skeletons are intentionally tiny: no downloads, installs or code execution.
    if key == "python":
        files = {"src/main.py": (
            'def main() -> None:\n    print("Hello, Grinder")\n\n\n'
            'if __name__ == "__main__":\n    main()\n'
        )}
    elif key == "node":
        files = {"src/index.js": 'console.log("Hello, Grinder");\n'}
    elif key == "go":
        files = {"main.go": (
            'package main\n\nimport "fmt"\n\n'
            'func main() { fmt.Println("Hello, Grinder") }\n'
        )}
    elif key == "rust":
        files = {"src/main.rs": 'fn main() { println!("Hello, Grinder"); }\n'}
    elif key == "java":
        files = {"src/main/java/Main.java": (
            'public class Main { public static void main(String[] args) {\n'
            '    System.out.println("Hello, Grinder");\n} }\n'
        )}
    elif key == "cpp":
        files = {"main.cpp": (
            '#include <iostream>\n'
            'int main() { std::cout << "Hello, Grinder\\n"; }\n'
        )}
    elif key == "csharp":
        files = {"Program.cs": 'Console.WriteLine("Hello, Grinder");\n'}
    else:
        files = {"README.md": "# My project\n\nLanguage-specific validation not configured.\n"}

    for relative, source in files.items():
        dest = directory / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(source, encoding="utf-8", errors="strict")

    if arch == "MVC":
        for subdirectory in ("models", "views", "controllers"):
            (directory / subdirectory).mkdir(exist_ok=True)
    if arch == "Clean":
        for subdirectory in ("domain", "application", "infrastructure"):
            (directory / subdirectory).mkdir(exist_ok=True)

    adapter = get_adapter(key, allow_build=allow_build)
    outcome = adapter.init_environment(directory)
    db = Database(directory / ".grinder" / "data.db")
    for setting, value in (("project_name", name), ("language", key), ("architecture", arch)):
        db.set_setting(setting, value)
    return InitResult(directory, outcome)


def interactive_init(parent: Path, *, allow_build: bool = False) -> InitResult:
    """Prompt for project metadata and create a skeleton offline by default."""
    name = input("Project name [my_project]: ").strip() or "my_project"
    print("Stacks: " + ", ".join(ADAPTERS))
    language = input("Language [python]: ").strip() or "python"
    architecture = input("Architecture (Minimal/MVC/Clean) [Minimal]: ").strip() or "Minimal"
    return create_project(parent, name, language, architecture, allow_build=allow_build)
