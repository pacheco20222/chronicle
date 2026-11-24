"""Read-only, bounded file catalog across a project's registered folders."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from heapq import nsmallest
import os
from pathlib import Path
import stat

from chronicle import registry
from chronicle.import_cli import SKIP_DIRS
from chronicle.vault.render import _frontmatter, _inert_source, _markdown_label, _source_link


@dataclass(frozen=True)
class CatalogEntry:
    folder: str
    relative_path: str
    absolute_path: str
    size: int
    modified: str


def _folder_files(folder: str, query: str | None) -> Iterator[CatalogEntry]:
    try:
        root = Path(folder).resolve()
    except (OSError, RuntimeError, ValueError):
        return
    for current, directories, filenames in os.walk(root, followlinks=False):
        directories[:] = [name for name in directories
                          if not name.startswith('.') and name not in SKIP_DIRS]
        for name in filenames:
            path = Path(current) / name
            relative = path.relative_to(root).as_posix()
            if name.startswith('.') or (query is not None and query not in relative.casefold()):
                continue
            try:
                resolved = path.resolve()
                if not resolved.is_relative_to(root):
                    continue
                if any(part.startswith(".") or part in SKIP_DIRS
                       for part in resolved.relative_to(root).parts):
                    continue
                metadata = path.stat()
                if not stat.S_ISREG(metadata.st_mode):
                    continue
                modified = datetime.fromtimestamp(metadata.st_mtime, timezone.utc).date().isoformat()
            except (OSError, RuntimeError, ValueError, OverflowError):
                continue
            yield CatalogEntry(folder, relative, str(path), metadata.st_size, modified)


def list_files(
    project: str, query: str | None = None, limit: int = 2000,
) -> tuple[list[CatalogEntry], bool]:
    """Return the first matching paths in folder/path order, retaining at most limit + 1."""
    if limit < 0:
        raise ValueError('limit must be non-negative')
    folders = registry.list_projects().get(project, [])
    folded = query.casefold() if query is not None else None
    candidates = (entry for folder in folders for entry in _folder_files(folder, folded))
    entries = nsmallest(limit + 1, candidates, key=lambda entry: (entry.folder, entry.relative_path))
    return entries[:limit], len(entries) > limit


def render_files(project: str, entries: list[CatalogEntry], truncated: bool) -> str:
    """Render a marked catalog using the shared source-link policy."""
    folders = registry.list_projects().get(project, [])
    lines = [f'# {_markdown_label(project)} files\n']
    if not folders:
        lines.append('No project folder registered\n')
    grouped: dict[str, list[CatalogEntry]] = {folder: [] for folder in folders}
    for entry in sorted(entries, key=lambda entry: (entry.folder, entry.relative_path)):
        grouped.setdefault(entry.folder, []).append(entry)
    for folder, files in sorted(grouped.items()):
        lines.append(f'## {_inert_source(folder)}\n')
        for entry in files:
            link = _source_link(entry.absolute_path, None, entry.relative_path)
            extension = Path(entry.relative_path).suffix.lstrip('.').lower() or 'no extension'
            lines.append(f'- {link} — {_markdown_label(extension)}, {entry.size} bytes, {entry.modified}')
        lines.append('')
    if truncated:
        lines.append(f'Truncated at {len(entries)} files\n')
    return _frontmatter(project=project) + '\n'.join(lines) + '\n'
