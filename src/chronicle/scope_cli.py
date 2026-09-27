import argparse
import sys

from chronicle.core.runtime import get_runtime


def _create(runtime, path: str) -> None:
    existing = {scope.path for scope in runtime.repository.list_scopes("")}
    scope = runtime.repository.get_or_create_scope(path)
    created = sorted(
        {item.path for item in runtime.repository.list_scopes("")} - existing,
        key=lambda item: (item.count("/"), item),
    )
    if created:
        print(f"Created scope(s): {', '.join(created)}")
    else:
        print(f"Scope already exists: {scope.path}")


def _list(runtime, prefix: str) -> None:
    for scope in runtime.list_scopes(prefix or ""):
        print(f"{'  ' * scope['path'].count('/')}{scope['path']}")


def _move(runtime, path: str, new_parent_path: str | None) -> None:
    try:
        scope = runtime.reparent_scope(path, new_parent_path)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
    print(f"Moved scope to {scope['path']}")


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="chronicle scope")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("path")

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--prefix", default="")

    move_parser = subparsers.add_parser("move")
    move_parser.add_argument("path")
    move_parser.add_argument("--to", default=None)

    args = parser.parse_args(argv)
    runtime = get_runtime()
    if args.command == "create":
        _create(runtime, args.path)
    elif args.command == "list":
        _list(runtime, args.prefix)
    else:
        _move(runtime, args.path, args.to)
