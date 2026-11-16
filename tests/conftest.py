"""Reusable isolated project fixture for all filesystem safety tests."""

from __future__ import annotations

import pytest

from grinder.database import Database
from grinder.file_ops import FileManager


@pytest.fixture
def setup(tmp_path):
    """Provide a clean project and project-local SQLite database."""
    root = tmp_path / "project"
    root.mkdir()
    db = Database(root / ".grinder" / "grinder.db")
    return root, db, FileManager(root, db)
