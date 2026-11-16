# Code Grinder (Мясорубка Кода) v2.2

**Stage 1 — recoverable, reviewed code-change core.** Code Grinder turns output from small local AI models (Ollama / LM Studio / Qwen / Llama) into syntax-checked, versioned file changes. It is **model-agnostic**. This repository deliberately delivers the core first; the CLI, Web UI, hot-folder watcher, language adapters and Project Map are **subsequent stages**, not implemented yet.

## Scope and security of Stage 1

- Parse multiple explicitly marked TARGET/MODE fenced code blocks as one batch.
- Modes: `CREATE`, `OVERWRITE`, `APPEND` (validate the combined file), and `PATCH` (unique exact SEARCH/REPLACE).
- Reject absolute paths, traversal, reserved metadata paths and symlinked/junction paths. On POSIX, source and destination operations use directory descriptors and `O_NOFOLLOW` to avoid symlinked-ancestor races; on Windows the fallback rechecks paths and junctions but cannot guarantee resistance against a malicious concurrent reparse-point swap. **Do not run the Windows stage against a directory writable by adversarial users.**
- Preview a unified diff without writing. Actual writes require `approved=True`; if validation is `SKIPPED`, they additionally require `allow_skipped=True`. Overwriting an untracked file additionally requires `allow_untracked=True`.
- Stage images in `.grinder_tmp/<transaction-id>/`, flush them, journal a `pending_transaction` in SQLite, then replace files one at a time. On caught errors, restore prior content. After process death, inspect pending state and explicitly choose rollback or completion.
- Store full version snapshots and SHA-256 checksums in SQLite; detect external changes before a new operation. A rollback becomes another version. The database and journal live under `.grinder/` and are ignored by git.
- Validate Python through non-executing `ast.parse`. Other languages return `SKIPPED` until their adapters are implemented in Stage 2. This is **syntax**, not semantic correctness, dependency validation or a security guarantee.

**Limitations:** This protocol implements *recoverable, compensating* multi-file transactions, **not an atomic filesystem transaction across multiple paths**. Other processes can momentarily observe an intermediate state. Directory-creation rollback is best-effort; manual changes and unknown hashes are never silently overwritten. Stage 1 handles UTF-8 text files up to 16 MiB each. No user-generated code is executed automatically; generated JavaScript or build scripts are never run in Stage 1.

## Input protocol

MODE is case-insensitive and can be on the TARGET line or the following line. All code must be in fenced Markdown blocks.

````text
TARGET: src/hello.py
MODE: CREATE
```python
print("Hello, Code Grinder!")
```

TARGET: src/settings.py MODE: OVERWRITE
EXPECTED_SHA256: 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
```python
DEBUG = False
```

TARGET: src/hello.py
MODE: PATCH
```text
<<<<<<< SEARCH
print("Hello, Code Grinder!")
=======
print("Hello, v2.2!")
>>>>>>> REPLACE
```
````

The optional `EXPECTED_SHA256` requires an exact match with the **current file** before PATCH or any other update; if it differs, nothing is written. The literal SEARCH section must match exactly once. The `APPEND` mode validates the **entire resulting source** after concatenation.

## Developer setup / current library API

Requires Python 3.12+. Preferred setup (assuming access to the package index):

```bash
uv sync
uv run pytest -q
uv run ruff check .
```

Minimal example for embedding the **Stage-1 library** in another trusted program:

```python
from pathlib import Path
from grinder.database import Database
from grinder.file_ops import FileManager
from grinder.parser import parse_response
from grinder.recovery import inspect, restore_pending

root = Path("./my_project").resolve()  # Existing directory
storage = Database(root / ".grinder" / "grinder.db")
manager = FileManager(root, storage)
issues = inspect(root, storage)
if issues:
    print("Review recovery issues before writing:", issues)
else:
    answer = "TARGET: hello.py\\nMODE: CREATE\\n```python\\nprint('hello')\\n```\\n"
    preview = manager.prepare(parse_response(answer))
    for change in preview:
        print(change.diff, change.validation.status, change.validation.detail)
    # Only call after the human has examined and approved ALL diffs:
    # manager.commit(preview, approved=True, allow_skipped=False)

# If a previous process was interrupted, after reviewing all files:
# restore_pending(root, storage, approved=True, strategy="rollback")
# or strategy="commit" to finish writing the proposed files.
```

`commit(...)` refuses to write without explicit approval. There is no web confirmation or `force_write` API route yet: those belong to Stage 4.

## Planned stages

1. **Stage 1 (this commit):** safe core, SQLite snapshots, PATCH, syntax statuses, unified diff, crash recovery and tests.
2. **Stage 2:** language environment adapters and project wizard.
3. **Stage 3:** Project Map L1/L2/L3 and model-specific prompt builders.
4. **Stage 4:** FastAPI web UI, preview/confirm dialogs, API and CLI.
5. **Stage 5:** watchdog-based inbox processing and batch automation.
6. **Stage 6:** cross-platform hardening, further fault-injection checks and release verification.

GitHub Actions runs `pytest` and `ruff` on Ubuntu and Windows. Passing Stage 1 unit tests is necessary but **not sufficient** to claim a production-ready release.

## License

MIT — see [LICENSE](LICENSE).

## Offline testing

When dependencies are **already installed**, run `python -m pytest` without
network access. `uv run --offline pytest` works only if *all* required packages
and a suitable Python interpreter are already available in the uv cache.
There is no `[tool.uv] offline = true` project setting; use the `--offline`
command-line flag or `UV_OFFLINE=1`.

GitHub Actions runs `uv sync`, `uv run pytest -q`, and `uv run ruff check .`
on Windows and Ubuntu. Do not treat local test success as confirmed CI success.

Windows details: guarded operations pin ancestor directory handles using
`CreateFileW` (without `FILE_SHARE_DELETE`), inspect `FILE_ATTRIBUTE_REPARSE_POINT`
and verify handle paths with `GetFinalPathNameByHandleW`. This closes the common
ancestor swap window. It is **not a complete guarantee against hostile concurrent
leaf replacement** or misconfigured ACLs. Keep projects private to one user.
