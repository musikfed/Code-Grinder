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
    """A concurrent ancestor swap must never redirect a rename outside the project."""
    from grinder import file_ops

    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    (project / "inside").mkdir()
    (project / "inside" / "file.py").write_text("old", encoding="utf-8")
    (outside / "file.py").write_text("DO NOT TOUCH", encoding="utf-8")
    db = Database(project / ".grinder" / "data.db")
    manager = FileManager(project, db)
    manager.stage(".grinder_tmp/tx/new-0", "new")
    original_replace = file_ops.replace_windows_staged
    injected = False
    swapped = False

    def simultaneous_swap(source: Path, leaf: str, parent_handle: int) -> None:
        nonlocal injected, swapped
        injected = True
        try:
            (project / "inside").rename(project / "detached")
            swapped = True
            # If possible, recreate an attacker-controlled junction at the old name.
            import subprocess

            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(project / "inside"), str(outside)],
                capture_output=True, text=True, check=False,
            )
        except OSError:
            pass  # A pinned directory may reject the hostile rename on NTFS.
        original_replace(source, leaf, parent_handle)

    monkeypatch.setattr(file_ops, "replace_windows_staged", simultaneous_swap)
    manager.replace_staged(".grinder_tmp/tx/new-0", "inside/file.py")
    assert injected
    assert (outside / "file.py").read_text(encoding="utf-8") == "DO NOT TOUCH"
    effective = project / ("detached" if swapped else "inside") / "file.py"
    assert effective.read_text(encoding="utf-8") == "new"
