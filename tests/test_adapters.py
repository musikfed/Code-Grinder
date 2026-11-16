"""Language adapter matrix: missing tools, checker outputs and opt-in policy."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from grinder.languages import ADAPTERS, adapter_for_file, get_adapter
from grinder.validator import Status, Validator


@pytest.mark.parametrize("language", ADAPTERS)
def test_adapter_environment_missing_tool_is_not_false_success(
    language: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Offline scaffolding succeeds but an absent compiler returns SKIPPED."""
    monkeypatch.setattr(shutil, "which", lambda name: None)
    folder = tmp_path / language
    folder.mkdir()
    adapter = get_adapter(language)
    assert adapter.init_environment(folder).status == Status.SKIPPED
    assert adapter.sync_dependencies(folder).status == Status.SKIPPED


@pytest.mark.parametrize("extension", [".js", ".ts", ".go", ".rs", ".java", ".cpp", ".cs", ".sql"])
def test_missing_checker_reports_skipped(
    extension: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No missing executable can be treated as syntax PASS."""
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert Validator().validate(Path("file" + extension), "some code").status == Status.SKIPPED


def test_python_ast_does_not_execute(tmp_path: Path) -> None:
    """No model-generated source executes during parser validation."""
    marker = tmp_path / "marker"
    code = f"__import__('pathlib').Path({str(marker)!r}).touch()\n"
    result = adapter_for_file(Path("sample.py")).validate(Path("sample.py"), code)
    assert result.status == Status.PASS
    assert not marker.exists()
    assert not (tmp_path / "__pycache__").exists()


def test_cpp_checker_invokes_compiler_without_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    """Compiler sees stdin only and -fsyntax-only; no executable output."""
    from grinder.languages.cpp_adapter import CppAdapter
    from grinder.validator import ValidationResult

    observed: list[str] = []
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/g++")

    def fake_run(args: list[str], **kwargs: object) -> ValidationResult:
        observed.extend(args)
        assert kwargs.get("source") == "int x;"
        return ValidationResult(Status.PASS, "OK")

    monkeypatch.setattr(CppAdapter, "run", staticmethod(fake_run))
    assert CppAdapter().validate(Path("x.cpp"), "int x;").status == Status.PASS
    assert observed[-4:] == ["-fsyntax-only", "-x", "c++", "-"]


def test_unknown_language_is_not_pass() -> None:
    """Unknown suffixes use the explicit SKIPPED adapter."""
    assert Validator().validate(Path("file.unknown"), "anything").status == Status.SKIPPED
