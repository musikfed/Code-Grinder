"""Marker parsing and path rejection tests."""

import pytest

from grinder.parser import Mode, ParseError, parse_response, validate_target


def test_parse_multiple_targets_and_inline_mode():
    """Small AI models may put MODE on the same line as TARGET."""
    response = '''TARGET: src/a.py MODE: CREATE
```python
x = 1
```
TARGET: src/b.py
MODE: OVERWRITE
EXPECTED_SHA256: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
```python
print("ok")
```
'''
    result = parse_response(response)
    assert len(result) == 2
    assert (result[0].target, result[0].mode, result[0].content) == (
        "src/a.py", Mode.CREATE, "x = 1\n",
    )
    assert result[1].expected_hash == "a" * 64


@pytest.mark.parametrize("value", [
    "../outside.py", "/etc/passwd", "C:/Windows/system.ini", r"..\escape.py",
    "src/../test.py", "src/./test.py", "//server/path", "src//a.py",
    ".git/config", ".grinder/db", ".grinder_tmp/payload", "~/.ssh/key",
])
def test_reject_dangerous_paths(value):
    """Cross-platform traversal and internals must always be rejected."""
    with pytest.raises(ParseError):
        validate_target(value)


def test_missing_markers_and_incomplete_batch():
    """Never process a non-protocol text reply or a partial batch."""
    with pytest.raises(ParseError):
        parse_response("print('hello')")
    with pytest.raises(ParseError):
        parse_response("TARGET: x.py\nMODE: CREATE\n```python\na = 1\n")
    with pytest.raises(ParseError):
        parse_response("TARGET: a.py\nMODE: CREATE\n```py\nx=1\n```\nTARGET: b.py")


def test_duplicate_targets_fail_entire_batch():
    """The same file must not appear twice in one change request."""
    text = "TARGET: A.py\nMODE: CREATE\n```python\nx=1\n```\n"
    text += "TARGET: a.py\nMODE: CREATE\n```python\nx=2\n```\n"
    with pytest.raises(ParseError, match="Duplicate"):
        parse_response(text)


def test_invalid_expected_hash_must_not_be_ignored():
    """Malformed concurrency guards must fail closed."""
    with pytest.raises(ParseError, match="Malformed"):
        parse_response("TARGET: a.py\nMODE: PATCH\nEXPECTED_SHA256: garbage\n"
                       "```text\ncontent\n```\n")
