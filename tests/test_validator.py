"""AST-only validation avoids executing model-supplied source."""

from pathlib import Path

from grinder.validator import Status, Validator


def test_python_ast_is_pass_without_execution(tmp_path):
    """The checker must not execute side effects or create bytecode caches."""
    marker = tmp_path / "executed.txt"
    source = f"open({str(marker)!r}, 'w').write('oops')\n"
    result = Validator().validate(tmp_path / "generated.py", source)
    assert result.status == Status.PASS
    assert not marker.exists()
    assert not (tmp_path / "__pycache__").exists()


def test_invalid_python_returns_fail():
    """SyntaxError is a definite FAIL, not an infrastructure ERROR."""
    result = Validator().validate(Path("broken.py"), "def broken(:\n")
    assert result.status == Status.FAIL


def test_unavailable_language_validation_is_skipped(monkeypatch):
    """No compiler or adapter may be reported as a successful check."""
    import shutil

    monkeypatch.setattr(shutil, "which", lambda _name: None)
    result = Validator().validate(Path("main.go"), "package main")
    assert result.status == Status.SKIPPED
