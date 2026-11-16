"""SQLite manifests, full snapshots, audit journal, and durable transaction intentions."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


def utcnow() -> str:
    """Return an offset-aware timestamp for audit events."""
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class ManifestEntry:
    """Most recent committed version of a tracked file."""

    file_path: str
    current_version: int
    file_hash: str
    last_updated: str


@dataclass(frozen=True)
class PendingTransaction:
    """Durable before- and after-images for one multi-file transaction."""

    txn_id: str
    state: str
    records: list[dict]
    created_at: str


class Database:
    """Persist all file metadata; filesystem changes occur in TransactionManager."""

    def __init__(self, db_path: Path) -> None:
        """Initialize a project-local SQLite database and its tables."""
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS manifest (
                    file_path TEXT PRIMARY KEY,
                    current_version INTEGER NOT NULL,
                    last_updated TEXT NOT NULL,
                    file_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    lines_count INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    UNIQUE(file_path, version)
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    txn_id TEXT,
                    file_path TEXT,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pending_transaction (
                    txn_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)

    def _connect(self) -> sqlite3.Connection:
        """Open one short-lived connection with a bounded busy wait."""
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=15000")
        return conn

    def get_manifest(self) -> list[ManifestEntry]:
        """List committed files in deterministic order."""
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM manifest ORDER BY file_path").fetchall()
        return [ManifestEntry(**dict(row)) for row in rows]

    def get_file(self, path: str) -> ManifestEntry | None:
        """Return committed metadata for one path, if any."""
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM manifest WHERE file_path=?", (path,)).fetchone()
        return ManifestEntry(**dict(row)) if row else None

    def get_history(self, path: str | None = None) -> list[dict]:
        """Return complete version entries, most recent first."""
        sql = "SELECT * FROM history"
        params: tuple[str, ...] = ()
        if path is not None:
            sql += " WHERE file_path=?"
            params = (path,)
        with closing(self._connect()) as conn:
            rows = conn.execute(sql + " ORDER BY id DESC", params).fetchall()
        return [dict(row) for row in rows]

    def get_version(self, path: str, version: int) -> str:
        """Read a past complete text snapshot for rollback."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT content FROM history WHERE file_path=? AND version=?", (path, version)
            ).fetchone()
        if row is None:
            raise LookupError(f"Unknown version {version} of {path}")
        return str(row["content"])

    def set_setting(self, key: str, value: str) -> None:
        """Upsert one persistent string preference."""
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) "
                "DO UPDATE SET value=excluded.value", (key, value),
            )

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        """Read a stored preference or return a default."""
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return str(row["value"]) if row else default

    def journal(
        self, txn_id: str | None, path: str | None, action: str, status: str, message: str
    ) -> None:
        """Append a durable audit event, not merely a console log."""
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO journal(txn_id,file_path,action,status,message,timestamp) "
                "VALUES (?,?,?,?,?,?)", (txn_id, path, action, status, message[:3000], utcnow()),
            )

    def get_journal(self) -> list[dict]:
        """Read audit records in creation order."""
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM journal ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def begin_pending(self, txn_id: str, records: list[dict]) -> None:
        """Record all before/after images durably before the first replacement."""
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO pending_transaction(txn_id,state,payload,created_at) "
                "VALUES (?, 'PREPARED', ?, ?)",
                (txn_id, json.dumps(records, ensure_ascii=False), utcnow()),
            )
            conn.execute(
                "INSERT INTO journal(txn_id,action,status,message,timestamp) "
                "VALUES (?, 'BATCH', 'PREPARED', ?, ?)",
                (txn_id, f"Prepared {len(records)} files", utcnow()),
            )

    def set_transaction_state(self, txn_id: str, state: str, message: str) -> None:
        """Persist a transaction phase transition and the reason."""
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                "UPDATE pending_transaction SET state=? WHERE txn_id=?", (state, txn_id)
            )
            if cursor.rowcount != 1:
                raise LookupError(f"Missing pending transaction {txn_id}")
            conn.execute(
                "INSERT INTO journal(txn_id,action,status,message,timestamp) "
                "VALUES (?, 'BATCH', ?, ?, ?)", (txn_id, state, message[:3000], utcnow()),
            )

    def pending(self) -> list[PendingTransaction]:
        """List outstanding batches requiring explicit resolution."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM pending_transaction ORDER BY created_at"
            ).fetchall()
        return [PendingTransaction(row["txn_id"], row["state"], json.loads(row["payload"]),
                                   row["created_at"]) for row in rows]

    def cancel_pending(self, txn_id: str, message: str) -> None:
        """Mark a successfully compensated batch as finished."""
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM pending_transaction WHERE txn_id=?", (txn_id,))
            conn.execute(
                "INSERT INTO journal(txn_id,action,status,message,timestamp) "
                "VALUES (?, 'BATCH', 'ROLLED_BACK', ?, ?)", (txn_id, message[:3000], utcnow()),
            )

    def commit_batch(self, txn_id: str, records: list[dict]) -> list[int]:
        """In one SQLite transaction, advance all versions and clear the pending record."""
        versions: list[int] = []
        with closing(self._connect()) as conn, conn:
            row = conn.execute(
                "SELECT state FROM pending_transaction WHERE txn_id=?", (txn_id,)
            ).fetchone()
            if row is None or row["state"] != "COMMITTING":
                raise RuntimeError("Cannot commit unprepared transaction")
            for record in records:
                previous = conn.execute(
                    "SELECT current_version,file_hash FROM manifest WHERE file_path=?",
                    (record["path"],),
                ).fetchone()
                if previous is not None and previous["file_hash"] != record["old_hash"]:
                    raise RuntimeError(f"Concurrent manifest update: {record['path']}")
                if previous is None and record["was_tracked"]:
                    raise RuntimeError(f"Manifest disappeared: {record['path']}")
                version = (previous["current_version"] if previous else 0) + 1
                now = utcnow()
                conn.execute(
                    "INSERT INTO manifest(file_path,current_version,last_updated,file_hash) "
                    "VALUES (?,?,?,?) ON CONFLICT(file_path) DO UPDATE SET "
                    "current_version=excluded.current_version,last_updated=excluded.last_updated, "
                    "file_hash=excluded.file_hash",
                    (record["path"], version, now, record["new_hash"]),
                )
                after = record["after"]
                conn.execute(
                    "INSERT INTO history(file_path,version,content,lines_count,action,timestamp) "
                    "VALUES (?,?,?,?,?,?)",
                    (record["path"], version, after, len(after.splitlines()),
                     record["action"], now),
                )
                versions.append(version)
            conn.execute("DELETE FROM pending_transaction WHERE txn_id=?", (txn_id,))
            conn.execute(
                "INSERT INTO journal(txn_id,action,status,message,timestamp) "
                "VALUES (?, 'BATCH', 'COMMITTED', ?, ?)",
                (txn_id, f"Committed {len(records)} files", utcnow()),
            )
        return versions
