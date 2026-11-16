"""SQLite manifest, history, settings, audit and pending transaction tests."""

from grinder.parser import Change, Mode


def test_versions_hashes_and_history(setup):
    """Each committed update should advance a version and persist a full snapshot."""
    root, db, manager = setup
    create = manager.prepare([Change("a.py", Mode.CREATE, "x = 1\n")])
    assert manager.commit(create, approved=True) == [1]
    overwrite = manager.prepare([Change("a.py", Mode.OVERWRITE, "x = 2\n")])
    assert manager.commit(overwrite, approved=True) == [2]
    assert db.get_file("a.py").current_version == 2
    assert db.get_version("a.py", 1) == "x = 1\n"
    assert db.get_version("a.py", 2) == "x = 2\n"
    assert len(db.get_history("a.py")) == 2
    assert not db.pending()
    assert (root / "a.py").read_text() == "x = 2\n"


def test_rollback_preserves_history(setup):
    """Rolling back must create another revision rather than deleting history."""
    _, db, manager = setup
    manager.commit(manager.prepare([Change("a.py", Mode.CREATE, "a = 1\n")]), approved=True)
    manager.commit(manager.prepare([Change("a.py", Mode.OVERWRITE, "a = 2\n")]), approved=True)
    assert manager.rollback("a.py", 1, approved=True) == [3]
    assert db.get_version("a.py", 3) == "a = 1\n"
    assert db.get_history("a.py")[0]["action"] == "ROLLBACK"


def test_settings_and_journal(setup):
    """Persist preferences and durable audit events in SQLite."""
    _, db, manager = setup
    db.set_setting("language", "Python")
    db.set_setting("language", "Rust")
    assert db.get_setting("language") == "Rust"
    assert db.get_setting("absent", "default") == "default"
    manager.commit(manager.prepare([Change("x.py", Mode.CREATE, "x = 1\n")]), approved=True)
    statuses = {entry["status"] for entry in db.get_journal()}
    assert {"PREPARED", "COMMITTING", "COMMITTED"} <= statuses
