"""Code Grinder CLI: stage 2 provides safe project scaffolding."""

from __future__ import annotations

import argparse
from pathlib import Path

from grinder.languages import ADAPTERS
from grinder.wizard import create_project, interactive_init


def main(argv: list[str] | None = None) -> int:
    """Parse CLI and initialize a new project; no network required by default."""
    parser = argparse.ArgumentParser(prog="Code Grinder")
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init", help="Create an offline-safe project skeleton")
    initialize.add_argument("--name", help="Project directory name; prompts when omitted")
    initialize.add_argument("--language", choices=ADAPTERS, help="Language stack")
    initialize.add_argument("--architecture", choices=("Minimal", "MVC", "Clean"))
    initialize.add_argument("--directory", type=Path, default=Path.cwd())
    initialize.add_argument(
        "--allow-build", action="store_true",
        help="Explicitly allow language environment initialization; may run installed tools",
    )
    args = parser.parse_args(argv)
    if args.command == "init":
        if all([args.name, args.language, args.architecture]):
            result = create_project(
                args.directory, args.name, args.language, args.architecture,
                allow_build=args.allow_build,
            )
        else:
            result = interactive_init(args.directory, allow_build=args.allow_build)
        print(f"Created: {result.path}")
        print(f"Environment: {result.adapter_status.status} — {result.adapter_status.detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
