"""Java source validation with annotation processing explicitly disabled."""

from __future__ import annotations

import tempfile
from pathlib import Path

from grinder.languages.base import BaseEnvAdapter
from grinder.validator import Status, ValidationResult


class JavaAdapter(BaseEnvAdapter):
    """Use javac -proc:none with an empty classpath for source syntax checking."""

    name = "java"
    extensions = (".java",)

    def init_environment(self, project_dir: Path) -> ValidationResult:
        """Record a basic Maven project without executing Maven plugins."""
        pom = project_dir / "pom.xml"
        if not pom.exists():
            pom.write_text(
                '<project xmlns="http://maven.apache.org/POM/4.0.0" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                'xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 '
                'https://maven.apache.org/xsd/maven-4.0.0.xsd">\n'
                '<modelVersion>4.0.0</modelVersion>\n'
                f'<groupId>local.grinder</groupId>'
                f'<artifactId>{project_dir.name.lower()}</artifactId>'
                '<version>0.1.0</version><properties><maven.compiler.release>17'
                '</maven.compiler.release></properties></project>\n',
                encoding="utf-8",
            )
        return (ValidationResult(Status.PASS, "pom.xml ready")
                if self.tool("javac", "mvn") else self.missing("javac / mvn"))

    def sync_dependencies(self, project_dir: Path) -> ValidationResult:
        """Maven dependency resolution requires opt-in to plugin execution/network."""
        if not self.allow_build:
            return ValidationResult(Status.SKIPPED, "Maven requires allow_build")
        mvn = self.tool("mvn")
        return (self.run([mvn, "dependency:resolve"], cwd=project_dir, timeout=120)
                if mvn else self.missing("mvn"))

    def validate(self, file_path: Path, content: str) -> ValidationResult:
        """Check Java source with -proc:none and isolated temp source/output paths."""
        javac = self.tool("javac")
        if not javac:
            return self.missing("javac")
        try:
            with tempfile.TemporaryDirectory(prefix="grinder-javac-") as directory:
                root = Path(directory)
                src = root / file_path.name
                src.write_text(content, encoding="utf-8")
                return self.run(
                    [javac, "-proc:none", "-classpath", str(root), "-sourcepath",
                     str(root), "-d", str(root), str(src)], cwd=root,
                )
        except OSError as exc:
            return ValidationResult(Status.ERROR, f"Java temp source failed: {exc}")
