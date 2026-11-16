"""Mid-batch faults, crash simulation, and explicit recovery tests."""

import pytest

from grinder.file_ops import SafetyError
from grinder.parser import Change, Mode
from grinder.recovery import inspect, restore_pending


def _setup_pair(manager):
    """Create two tracked files for a multi-file update."""
    manager.commit(manager.prepare([
        Change("a.py", Mode.CREATE, "a = 1\n"),
        Change("b.py", Mode.CREATE, "b = 1\n"),
    ]), approved=True)


def test_error_on_second_file_rolls_back_both(setup, monkeypatch):
    """A caught replacement failure must compensate the first replaced file."""
    root, db, manager = setup
    _setup_pair(manager)
    original = manager.replace_staged
    counter = 0

    def fail_second(source, target):
        nonlocal counter
        counter += 1
        if counter == 2:
            raise OSError("injected failure on second file")
        return original(source, target)

    monkeypatch.setattr(manager, "replace_staged", fail_second)
    preview = manager.prepare([
        Change("a.py", Mode.OVERWRITE, "a = 2\n"),
        Change("b.py", Mode.OVERWRITE, "b = 2\n"),
    ])
    with pytest.raises(SafetyError, match="reverted"):
        manager.commit(preview, approved=True)
    assert (root / "a.py").read_text() == "a = 1\n"
    assert (root / "b.py").read_text() == "b = 1\n"
    assert [db.get_file(name).current_version for name in ("a.py", "b.py")] == [1, 1]
    assert not db.pending()


def test_crash_after_first_replace_then_explicit_rollback(setup, monkeypatch):
    """A simulated process death leaves a record that restores the original pair."""
    root, db, manager = setup
    _setup_pair(manager)
    original = manager.replace_staged
    calls = 0

    def crash_on_second(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt("simulated abrupt exit")
        return original(source, target)

    monkeypatch.setattr(manager, "replace_staged", crash_on_second)
    preview = manager.prepare([
        Change("a.py", Mode.OVERWRITE, "a = 2\n"),
        Change("b.py", Mode.OVERWRITE, "b = 2\n"),
    ])
    with pytest.raises(KeyboardInterrupt):
        manager.commit(preview, approved=True)
    assert (root / "a.py").read_text() == "a = 2\n"
    assert (root / "b.py").read_text() == "b = 1\n"
    assert len(db.pending()) == 1
    assert inspect(root, db)
    with pytest.raises(SafetyError, match="Unresolved"):
        manager.prepare([Change("new.py", Mode.CREATE, "ok = True\n")])
    with pytest.raises(SafetyError, match="confirmation"):
        restore_pending(root, db)
    assert restore_pending(root, db, approved=True) == 2
    assert (root / "a.py").read_text() == "a = 1\n"
    assert (root / "b.py").read_text() == "b = 1\n"
    assert not db.pending()


def test_recover_crash_by_finish_commit(setup, monkeypatch):
    """An operator can instead finish the remaining staged changes."""
    root, db, manager = setup
    _setup_pair(manager)
    original = manager.replace_staged
    count = 0

    def crash(source, target):
        nonlocal count
        count += 1
        if count == 2:
            raise KeyboardInterrupt("abrupt")
        return original(source, target)

    monkeypatch.setattr(manager, "replace_staged", crash)
    preview = manager.prepare([
        Change("a.py", Mode.OVERWRITE, "a = 2\n"),
        Change("b.py", Mode.OVERWRITE, "b = 2\n"),
    ])
    with pytest.raises(KeyboardInterrupt):
        manager.commit(preview, approved=True)
    assert restore_pending(root, db, approved=True, strategy="commit") == 2
    assert (root / "a.py").read_text() == "a = 2\n"
    assert (root / "b.py").read_text() == "b = 2\n"
    assert db.get_file("b.py").current_version == 2


def test_conflict_blocks_recovery_without_clobber(setup, monkeypatch):
    """Manual changes after a crash must not be overwritten by recovery."""
    root, db, manager = setup
    _setup_pair(manager)
    original = manager.replace_staged
    count = 0

    def crash(source, target):
        nonlocal count
        count += 1
        if count == 2:
            raise KeyboardInterrupt("abrupt")
        return original(source, target)

    monkeypatch.setattr(manager, "replace_staged", crash)
    preview = manager.prepare([
        Change("a.py", Mode.OVERWRITE, "a = 2\n"),
        Change("b.py", Mode.OVERWRITE, "b = 2\n"),
    ])
    with pytest.raises(KeyboardInterrupt):
        manager.commit(preview, approved=True)
    (root / "a.py").write_text("a = 99\n")
    with pytest.raises(SafetyError, match="External change"):
        restore_pending(root, db, approved=True)
    assert (root / "a.py").read_text() == "a = 99\n"
    assert db.pending()[0].state == "CONFLICT"
