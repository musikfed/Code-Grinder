"""Windows-specific handle pinning: skipped on other operating systems."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from grinder.database import Database
from grinder.file_ops import FileManager, SafetyError

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows path race tests")


def test_windows_guard_rejects_junction(tmp_path: Path) -> None:
    """An ancestor junction is rejected rather than followed outside the project."""
    import subprocess

    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    junction = project / "linked"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        pytest.skip("mklink /J is unavailable in this runner")
    manager = FileManager(project, Database(project / ".grinder" / "data.db"))
    with pytest.raises(SafetyError):
        manager.safe_path("linked/source.py")


def test_race_condition_windows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pinned directory handles deny a concurrent ancestor rename during replace."""
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    (project / "inside").mkdir()
    (project / "inside" / "file.py").write_text("old", encoding="utf-8")
    db = Database(project / ".grinder" / "data.db")
    manager = FileManager(project, db)
    manager.stage(".grinder_tmp/tx/new-0", "new")
    original_replace = os.replace
    intercepted = False

    def simultaneous_rename(source: object, target: object, **kwargs: object) -> None:
        nonlocal intercepted
        intercepted = True
        with pytest.raises(PermissionError):
            (project / "inside").rename(project / "detached")
        original_replace(source, target, **kwargs)

    monkeypatch.setattr(os, "replace", simultaneous_rename)
    manager.replace_staged(".grinder_tmp/tx/new-0", "inside/file.py")
    assert intercepted
    assert (project / "inside" / "file.py").read_text(encoding="utf-8") == "new"
    assert not (outside / "file.py").exists()
