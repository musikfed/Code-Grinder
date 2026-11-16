# Code Grinder v2.2 — workflow diagrams, UI concepts and guides

This page documents **implemented Stage 1 and 2 capabilities** and separates them from **planned browser UI**. Nothing on the public GitHub Pages site accesses or modifies your local files.

## Working architecture

![Data flow](diagrams/flow.svg)

1. A local AI model outputs explicit `TARGET` and `MODE` Markdown blocks.
2. The parser reads them as an all-or-nothing batch.
3. Paths and content are validated; unknown compilers produce `SKIPPED`, not `PASS`.
4. `FileManager.prepare()` returns validated previews and unified Diff; no writes yet.
5. Only explicit human approval permits `FileManager.commit()` to persist staged changes, update snapshots and log the operation.
6. A transaction interrupted after individual file replacements requires explicit inspection and recovery.

## Recovery model

![Recovery](diagrams/transaction.svg)

The implementation uses a **recoverable multi-file operation**, not a globally atomic filesystem transaction. An external reader can briefly observe an intermediate state. SHA-256 detects unexpected on-disk edits. On Windows, guard handles and path checks limit but do not completely rule out malicious concurrent path swapping.

## Language adapter registry

![Adapters](diagrams/adapters.svg)

Python AST; Node.js JavaScript `--check`; Go `gofmt`; Rust `rustfmt`; Java `javac -proc:none`; C++ `g++`/`clang++ -fsyntax-only`; C# and NoOp return `SKIPPED` when no safe syntax-only check is offered. Some formats, including TypeScript and JSX, are deliberately skipped rather than falsely reported as verified. No builds run silently.

## UI concept images (not an implemented server)

| AI output editor | Diff preview |
|---|---|
| ![Editor concept](screenshots/editor.png) | ![Diff concept](screenshots/diff.png) |

| Version history | Project settings |
|---|---|
| ![History concept](screenshots/history.png) | ![Settings concept](screenshots/settings.png) |

**Important:** these images are screenshots of a designed browser-only concept. The web server, `serve` command, processing API, hot folder and Project Map are **not** part of Stage 2. They must not be represented as production features.

## Eight translations / 8 языков

[Русский](i18n/ru.md) · [English](i18n/en.md) · [한국어](i18n/ko.md) · [简体中文](i18n/zh.md) · [日本語](i18n/ja.md) · [Français](i18n/fr.md) · [Deutsch](i18n/de.md) · [Беларуская](i18n/be.md)

The source-code comments and public APIs remain in English for maintainability. The guides contain localized *explanatory code comments* and translations of usage/safety instructions.

**Standalone project page:** https://musikfed.github.io/view_my_prj/projects/Code-Grinder/
