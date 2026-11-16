"""Wizard and CLI operate offline without clobbering projects."""

from __future__ import annotations

from pathlib import Path

import pytest

from grinder.database import Database
from grinder.languages import ADAPTERS
from grinder.wizard import create_project
from main import main


@pytest.mark.parametrize("language", ADAPTERS)
def test_create_every_project_stack(tmp_path: Path, language: str) -> None:
    """Each supported stack gets a skeleton and persistent settings."""
    name = "demo_" + language
    result = create_project(tmp_path, name, language, "Minimal")
    assert result.path.is_dir()
    db = Database(result.path / ".grinder" / "data.db")
    assert db.get_setting("language") == language
    assert db.get_setting("project_name") == name
    assert any(result.path.rglob("*"))


def test_refuse_overwrite_existing_project(tmp_path: Path) -> None:
    """A second wizard run never silently destroys a project."""
    create_project(tmp_path, "demo", "python")
    with pytest.raises(FileExistsError):
        create_project(tmp_path, "demo", "go")


@pytest.mark.parametrize("unsafe", ["..", ".evil", "hello/world", "C:evil", "demo\\bad"])
def test_bad_name_rejected(tmp_path: Path, unsafe: str) -> None:
    """A project name cannot escape the chosen parent folder."""
    with pytest.raises(ValueError):
        create_project(tmp_path, unsafe)


def test_cli_init_noninteractive(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """python main.py init with flags initializes without terminal prompts."""
    code = main(["init", "--name", "hello", "--language", "python",
                 "--architecture", "Clean", "--directory", str(tmp_path)])
    assert code == 0
    assert (tmp_path / "hello" / "src" / "main.py").exists()
    assert (tmp_path / "hello" / "domain").exists()
    assert "Created:" in capsys.readouterr().out
