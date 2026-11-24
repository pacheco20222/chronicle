"""Command-line access to the rebuildable vault mirror."""

import argparse
from dataclasses import asdict
from pathlib import Path
import sys

from chronicle import registry
from chronicle.core.runtime import get_runtime
from chronicle.vault import settings
from chronicle.vault.mirror import mirror_for


def _print_result(result) -> None:
    result.raise_for_error()
    data = asdict(result)
    line = (f"{data['project']}: {data['written']} written, "
            f"{data['unchanged']} unchanged, {data['deleted']} deleted")
    if data['skipped']:
        line += f", {len(data['skipped'])} skipped"
    print(line)


def _print_status(data: dict) -> None:
    print(f"Vault: {data['vault'] or 'not configured'}")
    for project, count in data['projects'].items():
        print(f"{project}: {count} pages")
    for key in ('last_sync', 'last_refresh', 'last_error'):
        print(f"{key}: {data.get(key)}")
    skipped = sorted(set(data.get('skipped_user_files', []))
                     | set(data.get('last_refresh_skipped_user_files', [])))
    if skipped:
        print('Skipped user files:')
        for path in skipped:
            print(path)


def _run(args) -> None:
    if args.command == 'set':
        print(f"Vault: {settings.set_vault_path(Path(args.path))}")
        return
    mirror = mirror_for(get_runtime())
    if args.command == 'status':
        _print_status(mirror.status())
        return
    if args.command == 'add':
        _print_result(mirror.add_project(args.project))
    elif args.command == 'remove':
        print(f'{args.project}: {mirror.remove_project(args.project)} deleted')
    else:
        results = [mirror.sync_project(args.project)] if args.project is not None else mirror.sync_all()
        for result in results:
            _print_result(result)


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog='chronicle vault')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('set', help='set the vault folder').add_argument('path')
    for command in ('add', 'remove'):
        commands.add_parser(command, help=f'{command} a mirrored project').add_argument('project')
    commands.add_parser('status', help='show mirror status and diagnostics')
    commands.add_parser('sync', help='rebuild mirrored pages').add_argument('project', nargs='?')
    args = parser.parse_args(argv)
    try:
        _run(args)
    except (ValueError, OSError, RuntimeError, registry.RegistryError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
