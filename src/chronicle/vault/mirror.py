"""Rebuildable Obsidian projection of explicitly opted-in projects."""
from dataclasses import dataclass, field
import os
from pathlib import Path

from chronicle import config
from chronicle.vault import catalog, settings
from chronicle.vault.paths import chronicle_root, inside_root, memory_file, project_dir, project_folder_name
from chronicle.vault.projection import Projection, affected_memories, inbound
from chronicle.vault.render import render_index, render_log, render_memory, render_project
from chronicle.vault.state import read_status, record_status
from chronicle.vault.writer import delete_page, is_generated, write_page


@dataclass
class SyncResult:
    project: str
    written: int = 0
    unchanged: int = 0
    deleted: int = 0
    skipped: list[str] = field(default_factory=list)


def _folder(vault: Path, project: str) -> Path:
    expected = chronicle_root(vault) / project_folder_name(project)
    resolved = project_dir(vault, project)
    if resolved != expected:
        raise ValueError(f'refusing symlinked project folder: {expected}')
    return resolved


def _files(vault: Path, folder: Path):
    for current, directories, filenames in os.walk(folder, followlinks=False):
        directories[:] = [name for name in directories
                          if name != 'topics' and not (Path(current) / name).is_symlink()]
        for name in sorted(filenames):
            path = Path(current) / name
            inside_root(vault, path)
            if path.is_symlink():
                raise ValueError(f'refusing symlinked page: {path}')
            yield path


class VaultMirror:
    def __init__(self, service):
        self.service = service

    def _vault(self) -> Path | None:
        vault = settings.vault_path()
        if vault is not None and not vault.is_dir():
            raise FileNotFoundError(f'vault folder unavailable: {vault}')
        return vault.resolve() if vault is not None else None

    def _write(self, vault: Path, path: Path, text: str, result: SyncResult) -> None:
        if path.is_symlink():
            raise ValueError(f'refusing symlinked page: {path}')
        path = inside_root(vault, path)
        previous = path.read_text(encoding='utf-8') if path.exists() and is_generated(path) else None
        if not write_page(vault, path, text):
            result.skipped.append(str(path))
        elif previous == text:
            result.unchanged += 1
        else:
            result.written += 1

    def _render(self, vault: Path, project: str, projection: Projection,
                result: SyncResult, ids: set[str] | None = None) -> set[Path]:
        folder = _folder(vault, project)
        memories, links = projection.memories[project], projection.links
        expected = {folder / f'{project_folder_name(project)}.md', folder / 'log.md', folder / 'files.md'}
        for memory in memories:
            path = memory_file(vault, project, links[memory['id']].stem)
            expected.add(path)
            if ids is not None and memory['id'] not in ids:
                continue
            text = render_memory(memory, links, vault)
            if ids is not None and path.exists() and is_generated(path):
                # Keep the last sync's semantic graph until the next explicit sync.
                previous = path.read_text(encoding='utf-8').rsplit('\n\n## Links\n\n', 1)[-1]
                text += ''.join(line + '\n' for line in previous.splitlines()
                                if line.startswith('similar: ') and line not in text.splitlines())
            self._write(vault, path, text, result)
        overview = next((memory['content'] for memory in memories if memory.get('slug') == project), None)
        self._write(vault, folder / f'{project_folder_name(project)}.md',
                    render_project(project, overview, memories, vault, links), result)
        self._write(vault, folder / 'log.md', render_log(project, memories, links), result)
        return expected

    def on_memories_changed(self, ids: list[str]) -> None:
        try:
            if settings.vault_path() is None:
                return
            projects = settings.vault_projects()
            if not projects:
                return
            targets = self.service.repository.project_memory_ids(projects)
            relations = inbound(self.service, projects, targets)
            affected = affected_memories(self.service, ids, projects, relations)
            if not affected:
                return
            vault = self._vault()
            for project in affected:
                _folder(vault, project)
            write_ids = set().union(*affected.values())
            projection = Projection(self.service, vault, projects, list(affected), relations, write_ids)
            skipped = []
            for project, memory_ids in affected.items():
                result = SyncResult(project)
                self._render(vault, project, projection, result, memory_ids)
                skipped.extend(result.skipped)
            record_status(affected, skipped, refresh=True)
        except Exception as error:
            record_status(error=error, refresh=True)

    def sync_project(self, project: str) -> SyncResult:
        result = SyncResult(project)
        try:
            if not settings.is_mirrored(project):
                return result
            vault = self._vault()
            folder = _folder(vault, project)
            projection = Projection(self.service, vault, settings.vault_projects(), [project])
            if settings.similarity_links() and config.semantic_enabled():
                projection.add_similarity(self.service, project)
            expected = self._render(vault, project, projection, result)
            entries, truncated = catalog.list_files(project)
            self._write(vault, folder / 'files.md', catalog.render_files(project, entries, truncated), result)
            self._index(vault, result)
            for path in _files(vault, folder):
                if not is_generated(path):
                    result.skipped.append(str(path))
                elif path not in expected:
                    result.deleted += int(delete_page(vault, path))
            result.skipped = sorted(set(result.skipped))
            record_status([project], result.skipped)
        except Exception as error:
            record_status(skipped=result.skipped, error=error)
        return result

    def _index(self, vault: Path, result: SyncResult) -> None:
        projects = []
        for project in settings.vault_projects():
            overview = self.service.get_document(project, project)
            summary = overview['content'].splitlines()[0] if overview and overview['content'] else ''
            projects.append((project, summary))
        self._write(vault, chronicle_root(vault) / 'index.md', render_index(projects), result)

    def sync_all(self) -> list[SyncResult]:
        record_status()
        results = []
        last_error = None
        for project in settings.vault_projects():
            results.append(self.sync_project(project))
            last_error = read_status().get('last_error') or last_error
        if results:
            skipped = [path for result in results for path in result.skipped]
            record_status(skipped=skipped, error=RuntimeError(last_error) if last_error else None)
        return results

    def remove_project(self, project: str) -> int:
        result = SyncResult(project)
        try:
            settings.remove_project(project)
            vault = self._vault()
            if vault is not None:
                folder = _folder(vault, project)
                for path in _files(vault, folder):
                    if delete_page(vault, path):
                        result.deleted += 1
                    else:
                        result.skipped.append(str(path))
                self._remove_empty_dirs(folder)
            if vault is not None:
                self._index(vault, result)
            record_status(skipped=result.skipped)
        except Exception as error:
            failure = RuntimeError(f"generated files could not be deleted for project {project}: {error}")
            record_status(skipped=result.skipped, error=failure)
        return result.deleted

    @staticmethod
    def _remove_empty_dirs(folder: Path) -> None:
        for current, directories, filenames in os.walk(folder, topdown=False, followlinks=False):
            path = Path(current)
            if 'topics' in path.relative_to(folder).parts or path.is_symlink():
                continue
            if not any(path.iterdir()):
                path.rmdir()

    def status(self) -> dict:
        data = read_status()
        vault = settings.vault_path()
        data.update(vault=str(vault) if vault is not None else None, projects={})
        if vault is not None:
            for project in settings.vault_projects():
                try:
                    data['projects'][project] = sum(is_generated(path) for path in _files(vault, _folder(vault, project)))
                except Exception as error:
                    record_status(error=error)
                    data['last_error'] = str(error)
        return data
