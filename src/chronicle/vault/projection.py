"""Privacy-aware links, stable filenames, and scoped neighbor discovery."""
import json
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


def stable_stem(vault: Path, memory: dict) -> str:
    folder = project_dir(vault, memory['project']) / 'memories'
    if folder.resolve() != folder:
        raise ValueError(f'refusing symlinked memories folder: {folder}')
    for path in sorted(folder.glob(f'*-{memory["id"][:8]}.md')):
        inside_root(vault, path)
        if path.is_symlink():
            raise ValueError(f'refusing symlinked memory page: {path}')
        if page_id(path) == memory['id']:
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
    def __init__(self, service, vault: Path, projects: list[str], selected: list[str], relations=None):
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
        self.links = {key: LinkTarget(memory['project'], stable_stem(vault, memory), memory_title(memory['content']))
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
