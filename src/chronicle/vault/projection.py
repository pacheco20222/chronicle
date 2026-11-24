"""Privacy-aware links, stable filenames, and scoped neighbor discovery."""
import json
import os
import re
from pathlib import Path

from chronicle.core.graph import build_graph_data, explicit_relations
from chronicle.vault.paths import inside_root, memory_stem, memory_title, project_dir
from chronicle.vault.render import LinkTarget
from chronicle.vault.writer import is_generated


def page_id(path: Path) -> str | None:
    if not is_generated(path):
        return None
    with path.open(encoding='utf-8') as stream:
        header = stream.read(8192).split('\n---', 1)[0]
    for line in header.splitlines():
        if line.startswith('chronicle_id: '):
            try:
                value = json.loads(line.removeprefix('chronicle_id: '))
                return value if isinstance(value, str) else None
            except ValueError:
                return None
    return None


class StemIndex:
    """Scan each memory directory once; validate only collisions and write targets."""
    def __init__(self, vault: Path, projects: set[str], write_ids: set[str]):
        self.candidates: dict[str, dict[str, list[Path]]] = {}
        self.write_ids = write_ids
        self.confirmed: dict[Path, str | None] = {}
        for project in projects:
            self.candidates[project] = self._scan(vault, project)

    @staticmethod
    def _scan(vault: Path, project: str) -> dict[str, list[Path]]:
        folder = project_dir(vault, project) / 'memories'
        if folder.resolve() != folder:
            raise ValueError(f'refusing symlinked memories folder: {folder}')
        candidates: dict[str, list[Path]] = {}
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    match = re.search(r'-([0-9a-fA-F]{8})\.md$', entry.name)
                    if not match:
                        continue
                    path = Path(entry.path)
                    inside_root(vault, path)
                    if entry.is_symlink():
                        raise ValueError(f'refusing symlinked memory page: {path}')
                    if entry.is_file(follow_symlinks=False):
                        candidates.setdefault(match[1].lower(), []).append(path)
        except FileNotFoundError:
            pass
        return candidates

    def stem(self, memory: dict) -> str:
        candidates = self.candidates[memory['project']].get(memory['id'][:8].lower(), [])
        for path in sorted(candidates):
            if len(candidates) > 1 or memory['id'] in self.write_ids:
                if path not in self.confirmed:
                    self.confirmed[path] = page_id(path)
                if self.confirmed[path] != memory['id']:
                    continue
            return path.stem
        return memory_stem(memory['type'], memory['content'], memory['id'])


def mirrored_rows(service, ids, projects):
    ownership = service.repository.memory_projects(ids)
    allowed = [memory_id for memory_id, project in ownership.items() if project in projects]
    return service.repository.get_by_ids(allowed)


def inbound(service, projects, ids):
    return [relation for project in projects
            for relation in service.repository.inbound_relations(project, set(ids))]


def affected_memories(service, ids, projects, relations) -> dict[str, set[str]]:
    rows = mirrored_rows(service, ids, projects)
    affected = set(rows)
    for row in rows.values():
        affected.update(relation['target'] for relation in explicit_relations(service._serialize(row)))
    affected.update(source for source, _, target in relations if target in rows)
    ownership = service.repository.memory_projects(affected)
    result: dict[str, set[str]] = {}
    for memory_id, project in ownership.items():
        if project in projects:
            result.setdefault(project, set()).add(memory_id)
    return result


class Projection:
    def __init__(self, service, vault: Path, projects: list[str], selected: list[str], relations=None,
                 write_ids: set[str] | None = None):
        self.memories = {project: [service._serialize(row) for row in service.repository.all(project)]
                         for project in selected}
        records = {memory['id']: memory for memories in self.memories.values() for memory in memories}
        if relations is None:
            relations = inbound(service, projects, records)
        targets = set(records)
        for memory in records.values():
            memory['_inbound'] = []
            targets.update(relation['target'] for relation in explicit_relations(memory))
        for source, type_, target in relations:
            if target not in records:
                continue
            records[target]['_inbound'].append({'source': source, 'type': type_})
            targets.add(source)
        ownership = service.repository.memory_projects(targets - records.keys())
        extra = service.repository.get_by_ids([key for key, project in ownership.items() if project in projects])
        records.update({key: service._serialize(row) for key, row in extra.items()})
        if write_ids is None:
            write_ids = {memory["id"] for memories in self.memories.values() for memory in memories}
        stems = StemIndex(vault, {memory["project"] for memory in records.values()}, write_ids)
        self.links = {key: LinkTarget(memory['project'], stems.stem(memory), memory_title(memory['content']))
                      for key, memory in records.items()}
        for key in targets - self.links.keys():
            self.links[key] = LinkTarget(ownership.get(key, 'unknown'), None, '')

    def add_similarity(self, service, project: str) -> None:
        records = service.get_all_with_vectors(project)
        neighbors: dict[str, set[str]] = {}
        for edge in build_graph_data(records)['edges']:
            if edge['kind'] == 'semantic':
                neighbors.setdefault(edge['source'], set()).add(edge['target'])
                neighbors.setdefault(edge['target'], set()).add(edge['source'])
        for memory in self.memories[project]:
            memory['_similar'] = sorted(neighbors.get(memory['id'], set()) & self.links.keys())
