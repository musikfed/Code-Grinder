"""Windows-specific handle pinning: skipped on other operating systems."""

from __future__ import annotations

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
    """An ancestor replaced with a junction before the final check is rejected."""
    import subprocess

    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    (project / "inside").mkdir()
    (outside / "file.py").write_text("SAFE", encoding="utf-8")
    db = Database(project / ".grinder" / "data.db")
    manager = FileManager(project, db)
    manager.stage(".grinder_tmp/tx/new-0", "new")
    original_safe_path = manager.safe_path
    injected = False

    def inject_reparse(target: str, *, internal: bool = False) -> Path:
        nonlocal injected
        if target == "inside/file.py" and not injected:
            injected = True
            (project / "inside").rename(project / "detached")
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(project / "inside"), str(outside)],
                capture_output=True, text=True, check=False,
            )
            if result.returncode:
                pytest.skip("Cannot create test junction in this Windows runner")
        return original_safe_path(target, internal=internal)

    monkeypatch.setattr(manager, "safe_path", inject_reparse)
    with pytest.raises(SafetyError):
        manager.replace_staged(".grinder_tmp/tx/new-0", "inside/file.py")
    assert injected
    assert (outside / "file.py").read_text(encoding="utf-8") == "SAFE"
