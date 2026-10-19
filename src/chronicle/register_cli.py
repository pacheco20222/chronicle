import argparse
import sys
from pathlib import Path

from chronicle import registry


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="chronicle register")
    parser.add_argument("name", nargs="?", help="project name (same as --project)")
    parser.add_argument("--project", default=None)
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-register a folder that is already registered under a different project",
    )
    args = parser.parse_args(argv)

    if args.name and args.project and args.name != args.project:
        parser.error("give the project name once: either NAME or --project NAME")
    project = (args.project or args.name or "").strip()
    if not project:
        print("Error: a project name is required (chronicle register NAME).", file=sys.stderr)
        raise SystemExit(1)

    cwd = Path.cwd()
    try:
        registry.register(cwd, project, force=args.force)
    except registry.AlreadyRegisteredError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from None
    print(f"Registered {cwd.resolve()} as project '{project}'.")
