"""Secure paths, no-follow file descriptors, previews, and explicitly approved writes."""

from __future__ import annotations

import hashlib
import os
import stat
import threading
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path

from grinder.database import Database
from grinder.diff import unified_change
from grinder.parser import Change, Mode, validate_target
from grinder.patches import PatchError, apply_patch
from grinder.validator import Status, ValidationResult, Validator
from grinder.windows_guard import guard_windows_parents


class SafetyError(RuntimeError):
    """Reject unsafe or unexpected modifications instead of guessing."""


def sha256(content: str) -> str:
    """Hash the exact UTF-8 payload expected on disk."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PreparedChange:
    """A validated preview tied to the file's observed original hash."""

    source: Change
    path: Path
    before: str
    existed: bool
    before_hash: str | None
    after: str
    validation: ValidationResult
    diff: str
    untracked: bool


class FileManager:
    """Constrain file operations to the project and delegate batches to transactions."""

    MAX_FILE_BYTES = 16 * 1024 * 1024

    def __init__(self, project_dir: Path, database: Database, validator: Validator | None = None):
        """Bind a real project root, persistent metadata, and optional checker."""
        original = Path(project_dir)
        if original.is_symlink() or (hasattr(original, "is_junction") and original.is_junction()):
            raise SafetyError("Project root itself cannot be a symbolic link or junction")
        self.root = original.resolve(strict=True)
        if not self.root.is_dir():
            raise SafetyError("Project root must be a directory")
        self.database = database
        self.validator = validator or Validator()
        self._lock = threading.RLock()

    def safe_path(self, target: str, *, internal: bool = False) -> Path:
        """Reject absolute paths, traversal, and symlinked ancestors or final files."""
        if internal:
            if not (target.startswith(".grinder_tmp/") and ".." not in target.split("/")):
                raise SafetyError("Invalid internal staging path")
            parts = target.split("/")
        else:
            parts = validate_target(target).split("/")
        candidate = self.root.joinpath(*parts)
        cursor = self.root
        for component in parts:
            cursor /= component
            if cursor.is_symlink() or (hasattr(cursor, "is_junction") and cursor.is_junction()):
                raise SafetyError(f"Symbolic link/junction rejected: {target}")
        resolved = candidate.resolve(strict=False)
        if not resolved.is_relative_to(self.root) or resolved == self.root:
            raise SafetyError(f"Path escapes project: {target}")
        if candidate.exists() and not candidate.is_file():
            raise SafetyError(f"Not a regular file: {target}")
        return candidate

    @contextmanager
    def _parent_fd(self, relative: str, *, create: bool = False) -> Iterator[int | None]:
        """Open each parent by directory descriptor, refusing symlinks on POSIX.

        On Windows, pin parent-directory Win32 handles and use root-relative
        repeated lstat/realpath checks with an atomic os.replace operation.
        """
        parts = relative.split("/")[:-1]
        if os.name == "nt":
            # Keep real Win32 directory handles open (deny SHARE_DELETE) until
            # the caller finishes reading, creating, replacing or removing.
            path = self.root.joinpath(*relative.split("/"))
            with ExitStack() as guards:
                try:
                    pinned_parent = guards.enter_context(
                        guard_windows_parents(self.root, path, create=create)
                    )
                    self.safe_path(relative, internal=relative.startswith(".grinder_tmp/"))
                except (OSError, RuntimeError) as exc:
                    raise SafetyError(f"Windows path guard failed: {exc}") from exc
                # Do not wrap exceptions raised by the caller inside yield:
                # e.g. FileNotFoundError is a normal result of a new CREATE target.
                yield pinned_parent
            return
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        fd = os.open(self.root, flags)
        try:
            for part in parts:
                if create:
                    try:
                        os.mkdir(part, 0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                try:
                    next_fd = os.open(part, flags, dir_fd=fd)
                except FileNotFoundError:
                    raise
                except OSError as exc:
                    raise SafetyError(f"Unsafe parent directory {part}: {exc}") from exc
                os.close(fd)
                fd = next_fd
            yield fd
        finally:
            os.close(fd)

    def read(self, target: str) -> tuple[bool, str, str | None]:
        """Read a regular file with NOFOLLOW; preserve original LF/CRLF byte content."""
        self.safe_path(target)
        try:
            with self._parent_fd(target) as directory_fd:
                if os.name == "nt":
                    self.safe_path(target)
                    data = (self.root / target).read_bytes()
                else:
                    try:
                        fd = os.open(target.split("/")[-1], os.O_RDONLY | os.O_NOFOLLOW,
                                     dir_fd=directory_fd)
                    except FileNotFoundError:
                        return False, "", None
                    try:
                        info = os.fstat(fd)
                        if not stat.S_ISREG(info.st_mode):
                            raise SafetyError(f"Not a regular file: {target}")
                        if info.st_size > self.MAX_FILE_BYTES:
                            raise SafetyError("File exceeds the Stage-1 16 MiB limit")
                        chunks = []
                        remaining = self.MAX_FILE_BYTES + 1
                        while remaining > 0:
                            part = os.read(fd, min(remaining, 1024 * 1024))
                            if not part:
                                break
                            chunks.append(part)
                            remaining -= len(part)
                        data = b"".join(chunks)
                    finally:
                        os.close(fd)
        except FileNotFoundError:
            return False, "", None
        except (OSError, UnicodeDecodeError) as exc:
            raise SafetyError(f"Could not read {target}: {exc}") from exc
        if len(data) > self.MAX_FILE_BYTES:
            raise SafetyError("File exceeds the Stage-1 16 MiB limit")
        try:
            return True, data.decode("utf-8"), hashlib.sha256(data).hexdigest()
        except UnicodeDecodeError as exc:
            raise SafetyError(f"Expected UTF-8 text: {target}") from exc

    def stage(self, relative: str, content: str) -> None:
        """Persist one exclusive staging file on the project filesystem with fsync."""
        self.safe_path(relative, internal=True)
        with self._parent_fd(relative, create=True) as directory_fd:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if os.name != "nt":
                flags |= os.O_NOFOLLOW
            fd = os.open(
                (self.root / relative) if os.name == "nt" else relative.split("/")[-1],
                flags, 0o600, **({} if os.name == "nt" else {"dir_fd": directory_fd}),
            )
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(content.encode("utf-8"))
                    stream.flush()
                    os.fsync(stream.fileno())
            except BaseException:
                try:
                    self.unlink(relative, internal=True)
                except OSError:
                    pass
                raise

    def replace_staged(self, source: str, target: str) -> None:
        """Replace destination by descriptor-relative rename, never traversing symlinks."""
        self.safe_path(source, internal=True)
        self.safe_path(target)
        with self._parent_fd(source) as src_fd, self._parent_fd(target, create=True) as dst_fd:
            self.safe_path(target)
            if os.name == "nt":
                # Revalidate *both* path identities while parent handles are pinned.
                # Windows os.replace is a one-file atomic replacement, not a
                # security guarantee against malicious concurrent path swaps.
                self.safe_path(source, internal=True)
                self.safe_path(target)
                os.replace(self.root / source, self.root / target)
            else:
                os.replace(source.split("/")[-1], target.split("/")[-1],
                           src_dir_fd=src_fd, dst_dir_fd=dst_fd)
                os.fsync(dst_fd)

    def unlink(self, target: str, *, internal: bool = False) -> None:
        """Delete only the exact leaf within an anchored project directory."""
        self.safe_path(target, internal=internal)
        with self._parent_fd(target) as directory_fd:
            if os.name == "nt":
                (self.root / target).unlink(missing_ok=True)
            else:
                try:
                    os.unlink(target.split("/")[-1], dir_fd=directory_fd)
                except FileNotFoundError:
                    return
                os.fsync(directory_fd)

    def prepare(self, changes: list[Change]) -> list[PreparedChange]:
        """Preview and syntax-check a complete batch without modifying project files."""
        if not changes:
            raise SafetyError("Empty batch")
        if self.database.pending():
            raise SafetyError("Unresolved pending transaction; run recovery before new edits")
        results: list[PreparedChange] = []
        seen: set[str] = set()
        with self._lock:
            for change in changes:
                target = validate_target(change.target)
                path = self.safe_path(target)
                if target.casefold() in seen:
                    raise SafetyError(f"Duplicate TARGET in batch: {target}")
                seen.add(target.casefold())
                existed, before, before_hash = self.read(target)
                manifest = self.database.get_file(target)
                if manifest and manifest.file_hash != before_hash:
                    raise SafetyError(f"External/manual change detected: {target}")
                if change.expected_hash and change.expected_hash.lower() != before_hash:
                    raise SafetyError(f"EXPECTED_SHA256 mismatch: {target}")
                if change.mode == Mode.CREATE and existed:
                    raise SafetyError(f"CREATE target already exists: {target}")
                if change.mode in {Mode.APPEND, Mode.PATCH} and not existed:
                    raise SafetyError(f"Missing file for {change.mode}: {target}")
                try:
                    if change.mode == Mode.APPEND:
                        after = before + change.content
                    elif change.mode == Mode.PATCH:
                        after = apply_patch(before, change.content)
                    else:
                        after = change.content
                except PatchError as exc:
                    raise SafetyError(str(exc)) from exc
                if len(after.encode("utf-8")) > self.MAX_FILE_BYTES:
                    raise SafetyError("Proposed file exceeds the Stage-1 16 MiB limit")
                validation = self.validator.validate(path, after)
                if validation.status in {Status.FAIL, Status.ERROR}:
                    raise SafetyError(f"Validation {validation.status}: {validation.detail}")
                results.append(PreparedChange(
                    change, path, before, existed, before_hash, after, validation,
                    unified_change(before, after, target), existed and manifest is None,
                ))
        return results

    def commit(
        self, prepared: list[PreparedChange], *, approved: bool = False,
        allow_skipped: bool = False, allow_untracked: bool = False,
        action: str | None = None,
    ) -> list[int]:
        """Commit only with prior preview approval and explicit override for SKIPPED."""
        from grinder.transaction import TransactionManager

        if not approved:
            raise SafetyError("Diff approval is required before writing")
        return TransactionManager(self).commit(
            prepared, allow_skipped=allow_skipped, allow_untracked=allow_untracked,
            action=action,
        )

    def rollback(self, target: str, version: int, *, approved: bool = False) -> list[int]:
        """Restore a historical snapshot as a *new* version after approval."""
        previous = self.database.get_version(validate_target(target), version)
        preview = self.prepare([Change(target, Mode.OVERWRITE, previous)])
        return self.commit(preview, approved=approved, allow_skipped=True, action="ROLLBACK")
