"""Path safety, diff, approval, hashes and atomic replacement tests."""

import pytest

from grinder.file_ops import SafetyError
from grinder.parser import Change, Mode, ParseError
from grinder.validator import Status


def test_path_traversal_and_absolute_rejected(setup, tmp_path):
    """No TARGET may reference a path outside the workspace."""
    _, _, manager = setup
    for unsafe in ("../secret.py", "/tmp/secret.py", "C:/secret.py"):
        with pytest.raises((SafetyError, ParseError)):
            manager.prepare([Change(unsafe, Mode.CREATE, "x = 1\n")])
    assert not (tmp_path / "secret.py").exists()


def test_symlinked_parent_and_target_rejected(setup, tmp_path):
    """A link into another folder must never be followed to write data."""
    root, _, manager = setup
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (root / "linked").symlink_to(outside, target_is_directory=True)
        (root / "link.py").symlink_to(outside / "evil.py")
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is unavailable to this test account")
    with pytest.raises(SafetyError):
        manager.prepare([Change("linked/evil.py", Mode.CREATE, "x = 1\n")])
    with pytest.raises(SafetyError):
        manager.prepare([Change("link.py", Mode.CREATE, "x = 1\n")])
    assert not (outside / "evil.py").exists()


def test_diff_and_no_write_before_explicit_approval(setup):
    """Preview is read-only; unified diff displays exact +/- lines."""
    root, _, manager = setup
    manager.commit(manager.prepare([Change("a.py", Mode.CREATE, "x = 1\n")]), approved=True)
    preview = manager.prepare([Change("a.py", Mode.OVERWRITE, "x = 2\n")])
    assert "-x = 1" in preview[0].diff
    assert "+x = 2" in preview[0].diff
    with pytest.raises(SafetyError, match="approval"):
        manager.commit(preview)
    assert (root / "a.py").read_text() == "x = 1\n"


def test_manual_change_hash_blocks_overwrite(setup):
    """Optimistic concurrency must detect out-of-band edits."""
    root, _, manager = setup
    manager.commit(manager.prepare([Change("a.py", Mode.CREATE, "x = 1\n")]), approved=True)
    (root / "a.py").write_text("x = 99\n")
    with pytest.raises(SafetyError, match="manual"):
        manager.prepare([Change("a.py", Mode.OVERWRITE, "x = 2\n")])
    assert (root / "a.py").read_text() == "x = 99\n"


def test_skipped_validation_needs_force(setup):
    """Files without a validator must be rejected unless consciously overridden."""
    root, _, manager = setup
    changes = manager.prepare([Change("README.txt", Mode.CREATE, "hello\n")])
    assert changes[0].validation.status == Status.SKIPPED
    with pytest.raises(SafetyError, match="SKIPPED"):
        manager.commit(changes, approved=True)
    assert not (root / "README.txt").exists()
    assert manager.commit(changes, approved=True, allow_skipped=True) == [1]


def test_overwrite_untracked_needs_separate_permission(setup):
    """Pre-existing untracked files are not overwritten by accident."""
    root, _, manager = setup
    (root / "existing.py").write_text("a = 1\n")
    preview = manager.prepare([Change("existing.py", Mode.OVERWRITE, "a = 2\n")])
    with pytest.raises(SafetyError, match="Untracked"):
        manager.commit(preview, approved=True)
    manager.commit(preview, approved=True, allow_untracked=True)
    assert (root / "existing.py").read_text() == "a = 2\n"


def test_append_validates_combined_file(setup):
    """APPEND must be validated after concatenation, not in isolation."""
    _, _, manager = setup
    manager.commit(manager.prepare([Change("x.py", Mode.CREATE, "x = 1\n")]), approved=True)
    with pytest.raises(SafetyError, match="FAIL"):
        manager.prepare([Change("x.py", Mode.APPEND, "def broken(:\n")])


def test_symlink_swap_during_commit_cannot_write_outside(setup, tmp_path, monkeypatch):
    """A substituted parent symlink immediately before rename is blocked."""
    root, db, manager = setup
    (root / "dir").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    original = manager.replace_staged

    def swap_before_replace(source, target):
        (root / "dir").rename(root / "saved")
        try:
            (root / "dir").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            (root / "saved").rename(root / "dir")
            pytest.skip("Symlink creation is unavailable")
        original(source, target)

    monkeypatch.setattr(manager, "replace_staged", swap_before_replace)
    with pytest.raises(SafetyError):
        manager.commit(manager.prepare([Change("dir/evil.py", Mode.CREATE, "x = 1\n")]),
                       approved=True)
    assert not (outside / "evil.py").exists()
    # Unblock the path before resolving the durable pending record.
    (root / "dir").unlink()
    (root / "saved").rename(root / "dir")
    assert db.pending()
    from grinder.recovery import restore_pending
    assert restore_pending(root, db, approved=True) == 1
    assert not (root / "dir" / "evil.py").exists()


def test_patch_expected_hash_and_version(setup):
    """A versioned patch uses an exact hash precondition and preserves history."""
    root, db, manager = setup
    manager.commit(manager.prepare([Change("a.py", Mode.CREATE, "x = 1\n")]), approved=True)
    previous_hash = db.get_file("a.py").file_hash
    patch = "<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n>>>>>>> REPLACE\n"
    preview = manager.prepare([Change("a.py", Mode.PATCH, patch, previous_hash)])
    assert manager.commit(preview, approved=True) == [2]
    assert (root / "a.py").read_text() == "x = 2\n"
    with pytest.raises(SafetyError, match="SHA256"):
        manager.prepare([Change("a.py", Mode.PATCH, patch, previous_hash)])


def test_diff_stale_preview_blocks_commit(setup):
    """A manually edited file after preview cannot be overwritten."""
    root, _, manager = setup
    manager.commit(manager.prepare([Change("a.py", Mode.CREATE, "x = 1\n")]), approved=True)
    preview = manager.prepare([Change("a.py", Mode.OVERWRITE, "x = 3\n")])
    (root / "a.py").write_text("x = 99\n")
    with pytest.raises(SafetyError, match="manual"):
        manager.commit(preview, approved=True)
    assert (root / "a.py").read_text() == "x = 99\n"
