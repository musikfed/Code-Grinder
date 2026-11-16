"""Extensible language adapter registry, keyed by stack and extension."""

from __future__ import annotations

from pathlib import Path

from grinder.languages.base import BaseEnvAdapter
from grinder.languages.cpp_adapter import CppAdapter
from grinder.languages.csharp_adapter import CSharpAdapter
from grinder.languages.go_adapter import GoAdapter
from grinder.languages.java_adapter import JavaAdapter
from grinder.languages.node_adapter import NodeAdapter
from grinder.languages.noop_adapter import NoOpAdapter
from grinder.languages.python_adapter import PythonAdapter
from grinder.languages.rust_adapter import RustAdapter

ADAPTERS: dict[str, type[BaseEnvAdapter]] = {
    "python": PythonAdapter,
    "node": NodeAdapter,
    "go": GoAdapter,
    "rust": RustAdapter,
    "java": JavaAdapter,
    "cpp": CppAdapter,
    "csharp": CSharpAdapter,
    "noop": NoOpAdapter,
}


def get_adapter(name: str, *, allow_build: bool = False) -> BaseEnvAdapter:
    """Construct a stack adapter; unknown stacks are rejected explicitly."""
    key = name.strip().casefold()
    if key not in ADAPTERS:
        raise ValueError(f"Unsupported language stack: {name}")
    return ADAPTERS[key](allow_build=allow_build)


def adapter_for_file(path: Path, *, allow_build: bool = False) -> BaseEnvAdapter:
    """Find an adapter by extension; unknown suffixes use explicit SKIPPED."""
    suffix = path.suffix.lower()
    for adapter_class in ADAPTERS.values():
        if suffix in adapter_class.extensions:
            return adapter_class(allow_build=allow_build)
    return NoOpAdapter(allow_build=allow_build)
