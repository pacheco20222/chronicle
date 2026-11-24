"""Command-line access to the rebuildable vault mirror."""

import argparse
from dataclasses import asdict
from pathlib import Path
import sys

from chronicle import registry
from chronicle.core.runtime import get_runtime
from chronicle.vault import settings
from chronicle.vault.mirror import VaultMirror


def _print_result(result) -> None:
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
    service = get_runtime()
    mirror = next((observer.__self__ for observer in service.observers
                   if isinstance(getattr(observer, '__self__', None), VaultMirror)), None)
    mirror = mirror or VaultMirror(service)
    if args.command == 'status':
        _print_status(mirror.status())
        return
    if args.command == 'add':
        if settings.vault_path() is None:
            raise ValueError('no vault configured; run chronicle vault set <path> first')
        if not service.repository.project_exists(args.project) and args.project not in registry.list_projects():
            raise ValueError(f'project does not exist: {args.project}')
        settings.add_project(args.project)
        _print_result(mirror.sync_project(args.project))
    elif args.command == 'remove':
        print(f'{args.project}: {mirror.remove_project(args.project)} deleted')
    else:
        results = [mirror.sync_project(args.project)] if args.project is not None else mirror.sync_all()
        for result in results:
            _print_result(result)
    error = mirror.status().get('last_error')
    if error:
        raise RuntimeError(error)


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
