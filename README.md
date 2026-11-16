# Code Grinder (Мясорубка Кода) v2.2

**Stage 2 — language adapters and offline project wizard, built on the Stage-1
recoverable code-change core.** Code Grinder turns responses from small local AI
models (Ollama / LM Studio / Qwen / Llama) into reviewed, versioned file changes.
The CLI's `init` command is now implemented; web UI, process CLI, watcher and
Project Map remain future milestones. No dependency installs or builds happen
silently.

## Scope and security of Stage 1

- Parse multiple explicitly marked TARGET/MODE fenced code blocks as one batch.
- Modes: `CREATE`, `OVERWRITE`, `APPEND` (validate the combined file), and `PATCH` (unique exact SEARCH/REPLACE).
- Reject absolute paths, traversal, reserved metadata paths and symlinked/junction paths. On POSIX, parent-directory descriptors and `O_NOFOLLOW` protect from ancestor symlink races; on Windows parent handles are pinned via `CreateFileW` and file paths are rechecked immediately before `os.replace()`. This is not a complete hostile-user security boundary.
- Preview a unified diff without writing. Actual writes require `approved=True`; if validation is `SKIPPED`, they additionally require `allow_skipped=True`. Overwriting an untracked file additionally requires `allow_untracked=True`.
- Stage images in `.grinder_tmp/<transaction-id>/`, flush them, journal a `pending_transaction` in SQLite, then replace files one at a time. On caught errors, restore prior content. After process death, inspect pending state and explicitly choose rollback or completion.
- Store full version snapshots and SHA-256 checksums in SQLite; detect external changes before a new operation. A rollback becomes another version. The database and journal live under `.grinder/` and are ignored by git.
- Validate Python through non-executing `ast.parse`. Other languages use Stage-2 adapters where a safe checker is available. Unavailable or deliberately unsafe validation returns `SKIPPED`, never `PASS`. Passing syntax checks is **not** a guarantee of safe code.

**Limitations:** This protocol implements *recoverable, compensating* multi-file transactions, **not an atomic filesystem transaction across multiple paths**. Other processes can momentarily observe an intermediate state. Directory-creation rollback is best-effort; manual changes and unknown hashes are never silently overwritten. Stage 1 handles UTF-8 text files up to 16 MiB each. No user-generated application code is executed automatically; project build tools may execute user-provided scripts and require an explicit trusted workflow.

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

## Поддерживаемые языки / Supported languages

`python main.py init` starts the interactive wizard. For non-interactive setup:

```bash
python main.py init --name demo --language python --architecture Minimal --directory .
python main.py init --name demo_go --language go --architecture Clean --directory .
```

The wizard refuses to overwrite non-empty project directories; it creates a
language skeleton, optional MVC/Clean directories and saves settings in
`.grinder/data.db`. It does not automatically download dependencies or run builds.
Use the Python library's adapters with `allow_build=True` **only for trusted
projects**. A missing toolchain is reported as `SKIPPED`.

| Stack | Environment / manager | Default validation |
| --- | --- | --- |
| Python | uv, fallback venv/pip (explicit) | `ast.parse` (no execution) |
| Node.js | bun → pnpm → npm | `node --check -` for JS; TS/JSX `SKIPPED` |
| Go | go.mod, optional go mod tidy | `gofmt -e` parsing stdin |
| Rust | Cargo.toml, optional cargo fetch | `rustfmt --emit stdout` syntax parser |
| Java | Maven pom.xml | isolated `javac -proc:none` (no processors) |
| C++ | CMakeLists.txt | `g++` / `clang++ -fsyntax-only` |
| C# | SDK-style csproj | `SKIPPED` until trusted build path |
| NoOp | plain text / Bash / SQL / HTML / CSS | `SKIPPED` |

`rustc --emit=metadata`, `cargo check`, `dotnet build`, Maven and TypeScript
project tooling may execute macros/plugins/build scripts; they are **not** run
during default syntax validation. Shell execution is never used by adapters.

## Planned stages

1. **Stage 1 (complete):** safe core, SQLite snapshots, PATCH, syntax statuses, unified diff, crash recovery and tests.
2. **Stage 2 (this commit):** language adapters and offline project wizard.
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
`CreateFileW` (without `FILE_SHARE_DELETE`), inspect `FILE_ATTRIBUTE_REPARSE_POINT`,
and verify handle paths with `GetFinalPathNameByHandleW`. Windows staged replacements
use `os.replace()` after another no-reparse check. There is still a narrow
TOCTOU window against a malicious concurrent actor. It is **not a complete guarantee against hostile concurrent
leaf replacement** or misconfigured ACLs. Keep projects private to one user.


## 🌐 Visual workflow & multilingual guides

**Code Grinder v2.2 Stage 2** includes [illustrated flowcharts, recoverable transaction diagrams, adapter architecture and four web-UI *concept screenshots*](docs/SHOWCASE.md).

Guides, protocol explanations, safety notes, and localized explanatory code comments are available in eight languages:

[Русский](docs/i18n/ru.md) · [English](docs/i18n/en.md) · [한국어](docs/i18n/ko.md) · [简体中文](docs/i18n/zh.md) · [日本語](docs/i18n/ja.md) · [Français](docs/i18n/fr.md) · [Deutsch](docs/i18n/de.md) · [Беларуская](docs/i18n/be.md).

**[Interactive Code Grinder project showcase](https://musikfed.github.io/view_my_prj/projects/Code-Grinder/)** — independent static page. The pictured web interface is a design mockup only. The FastAPI web server, browser approvals and processing API have **not yet been implemented**.
