"""Read-only integrity inspection and explicitly approved crash recovery."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from grinder.database import Database
from grinder.file_ops import FileManager, SafetyError
from grinder.transaction import TransactionManager


@dataclass(frozen=True)
class RecoveryIssue:
    """A file with a detected inconsistency and human-readable cause."""

    file_path: str
    reason: str


def inspect(project_dir: Path, db: Database) -> list[RecoveryIssue]:
    """Report hash drift and interrupted transactions; never silently overwrite."""
    manager = FileManager(project_dir, db)
    issues: list[RecoveryIssue] = []
    pending_paths = {r["path"] for p in db.pending() for r in p.records}
    for entry in db.get_manifest():
        try:
            _, _, current_hash = manager.read(entry.file_path)
            if current_hash != entry.file_hash and entry.file_path not in pending_paths:
                issues.append(RecoveryIssue(entry.file_path, "Hash mismatch or missing file"))
        except (OSError, SafetyError) as exc:
            issues.append(RecoveryIssue(entry.file_path, str(exc)))
    for pending in db.pending():
        for record in pending.records:
            issues.append(RecoveryIssue(
                record["path"], f"Interrupted transaction {pending.txn_id}: {pending.state}"
            ))
    return issues


def restore_pending(
    project_dir: Path, db: Database, *, approved: bool = False,
    strategy: str = "rollback",
) -> int:
    """Restore incomplete batches only after explicit operator confirmation."""
    if not approved:
        raise SafetyError("Recovery requires explicit confirmation")
    engine = TransactionManager(FileManager(project_dir, db))
    restored = 0
    for pending in db.pending():
        restored += engine.restore(pending.txn_id, strategy=strategy)
    return restored
