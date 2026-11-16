"""C# adapter: builds are never invoked without explicit trust."""

from __future__ import annotations

from pathlib import Path

from grinder.languages.base import BaseEnvAdapter
from grinder.validator import Status, ValidationResult


class CSharpAdapter(BaseEnvAdapter):
    """C# project scaffolding; SDK builds only on explicit allow_build."""

    name = "csharp"
    extensions = (".cs",)

    def init_environment(self, project_dir: Path) -> ValidationResult:
        """Write SDK-style project file without invoking dotnet templates."""
        csproj = project_dir / f"{project_dir.name}.csproj"
        if not csproj.exists():
            csproj.write_text(
                '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
                '<OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework>'
                '<ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable>'
                '</PropertyGroup></Project>\n', encoding="utf-8",
            )
        return (ValidationResult(Status.PASS, "SDK-style .csproj ready")
                if self.tool("dotnet") else self.missing("dotnet"))

    def sync_dependencies(self, project_dir: Path) -> ValidationResult:
        """Restore packages only in trusted build mode."""
        if not self.allow_build:
            return ValidationResult(Status.SKIPPED, "dotnet restore requires allow_build")
        dotnet = self.tool("dotnet")
        return (self.run([dotnet, "restore"], cwd=project_dir, timeout=120)
                if dotnet else self.missing("dotnet"))

    def validate(self, file_path: Path, content: str) -> ValidationResult:
        """Do not silently build arbitrary C# project while parsing one source file."""
        return ValidationResult(
            Status.SKIPPED, "C# syntax-only parser unavailable; dotnet build is opt-in",
        )
