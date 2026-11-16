"""Recoverable prepare/commit protocol for batches of file changes.

This is a journaled, compensating transaction. os.replace is atomic per file;
multi-file readers can still observe an intermediate state during commit.
"""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from filelock import FileLock

from grinder.file_ops import SafetyError, sha256
from grinder.validator import Status

if TYPE_CHECKING:
    from grinder.file_ops import FileManager, PreparedChange


class TransactionManager:
    """Enforce review, stage all changes, journal intentions, and compensate failures."""

    def __init__(self, manager: FileManager) -> None:
        """Bind the filesystem and its SQLite metadata store."""
        self.manager = manager
        self.db = manager.database

    @contextmanager
    def _lock(self) -> Iterator[None]:
        """Serialize Code Grinder writers across processes on Windows and Linux."""
        directory = self.manager.root / ".grinder"
        if (directory.is_symlink()
                or (hasattr(directory, "is_junction") and directory.is_junction())):
            raise SafetyError("Refusing symlinked lock directory")
        directory.mkdir(exist_ok=True)
        with FileLock(str(directory / "grinder.lock"), timeout=15):
            yield

    def _clean_stage(self, txn_id: str) -> None:
        """Remove only our known staging directory after the journal is resolved."""
        stage = self.manager.root / ".grinder_tmp" / txn_id
        if stage.is_symlink() or (hasattr(stage, "is_junction") and stage.is_junction()):
            raise SafetyError("Staging directory replaced by link")
        if stage.is_dir():
            shutil.rmtree(stage)

    def commit(
        self, prepared: list[PreparedChange], *, allow_skipped: bool,
        allow_untracked: bool, action: str | None = None,
    ) -> list[int]:
        """Commit a previously approved batch, compensating any caught exceptions."""
        if not prepared:
            raise SafetyError("Cannot commit empty batch")
        with self._lock(), self.manager._lock:
            current = self.manager.prepare([entry.source for entry in prepared])
            if (len(current) != len(prepared) or any(
                a.before_hash != b.before_hash or a.after != b.after
                for a, b in zip(current, prepared, strict=True)
            )):
                raise SafetyError("Files changed after diff preview; review again")
            if any(p.validation.status == Status.SKIPPED for p in current) and not allow_skipped:
                raise SafetyError("SKIPPED validation requires explicit force_write/confirmation")
            if any(p.untracked for p in current) and not allow_untracked:
                raise SafetyError("Untracked existing file requires explicit permission")
            txn_id = uuid.uuid4().hex
            records: list[dict] = []
            pending = False
            try:
                # Stage every after-image plus before-images on the *same* filesystem.
                for i, entry in enumerate(current):
                    target = entry.source.target
                    stage_after = f".grinder_tmp/{txn_id}/new-{i}"
                    self.manager.stage(stage_after, entry.after)
                    if entry.existed:
                        self.manager.stage(f".grinder_tmp/{txn_id}/old-{i}", entry.before)
                    records.append({
                        "path": target,
                        "existed": entry.existed,
                        "was_tracked": not entry.untracked and entry.existed,
                        "before": entry.before,
                        "old_hash": entry.before_hash,
                        "after": entry.after,
                        "new_hash": sha256(entry.after),
                        "action": action or entry.source.mode.value,
                        "staged": stage_after,
                    })
                # No physical file is replaced until the intent is durable in SQLite.
                self.db.begin_pending(txn_id, records)
                pending = True
                self.db.set_transaction_state(txn_id, "COMMITTING", "Starting staged replacements")
                for record in records:
                    exists, _, actual = self.manager.read(record["path"])
                    if exists != record["existed"] or actual != record["old_hash"]:
                        raise SafetyError(f"File changed during transaction: {record['path']}")
                    self.manager.replace_staged(record["staged"], record["path"])
                versions = self.db.commit_batch(txn_id, records)
                return versions
            except Exception as exc:
                if pending:
                    try:
                        self.db.set_transaction_state(txn_id, "FAILED", f"Commit failed: {exc}")
                        self.restore(txn_id, strategy="rollback", lock_held=True)
                    except Exception as recovery_error:
                        raise SafetyError(
                            f"Batch failed; pending recovery needed ({recovery_error})"
                        ) from exc
                raise SafetyError(f"Batch rejected or reverted: {exc}") from exc
            finally:
                if not pending or not any(p.txn_id == txn_id for p in self.db.pending()):
                    self._clean_stage(txn_id)

    def restore(
        self, txn_id: str, *, strategy: str = "rollback", lock_held: bool = False
    ) -> int:
        """Explicitly rollback or finish an interrupted batch; reject unknown changes."""
        if strategy not in {"rollback", "commit"}:
            raise ValueError("Recovery strategy must be rollback or commit")
        if not lock_held:
            with self._lock():
                return self.restore(txn_id, strategy=strategy, lock_held=True)
        found = [t for t in self.db.pending() if t.txn_id == txn_id]
        if len(found) != 1:
            raise SafetyError(f"Pending transaction not found: {txn_id}")
        records = found[0].records
        # Verify the *entire* batch before changing a single file during recovery.
        for record in records:
            _, _, digest = self.manager.read(record["path"])
            if digest not in {record["old_hash"], record["new_hash"]}:
                self.db.set_transaction_state(txn_id, "CONFLICT", "External modifications")
                raise SafetyError(f"External change blocks recovery: {record['path']}")
        if strategy == "rollback":
            for i, record in enumerate(reversed(records)):
                target = record["path"]
                exists, _, current_hash = self.manager.read(target)
                if current_hash == record["old_hash"]:
                    continue
                if record["existed"]:
                    stage_name = f".grinder_tmp/{txn_id}/recover-{i}-{uuid.uuid4().hex}"
                    self.manager.stage(stage_name, record["before"])
                    self.manager.replace_staged(stage_name, target)
                elif exists:
                    self.manager.unlink(target)
            self.db.cancel_pending(txn_id, "Restored before-images after interrupted batch")
        else:
            self.db.set_transaction_state(txn_id, "COMMITTING", "Resuming interrupted batch")
            for i, record in enumerate(records):
                target = record["path"]
                _, _, actual = self.manager.read(target)
                if actual == record["new_hash"]:
                    continue
                stage = f".grinder_tmp/{txn_id}/resume-{i}-{uuid.uuid4().hex}"
                self.manager.stage(stage, record["after"])
                self.manager.replace_staged(stage, target)
            self.db.commit_batch(txn_id, records)
        self._clean_stage(txn_id)
        return len(records)
