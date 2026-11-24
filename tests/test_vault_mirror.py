"""Integration contract for the rebuildable, opt-in vault projection."""
import json
import shutil

import pytest

from chronicle.vault import settings
from chronicle.vault.paths import project_dir


@pytest.fixture
def mirror(service, tmp_path, monkeypatch):
    from chronicle.vault.mirror import VaultMirror

    monkeypatch.setenv('CHRONICLE_STATE_DIR', str(tmp_path / 'state'))
    result = VaultMirror(service)
    service.observers.append(result.on_memories_changed)
    return result


def configure(tmp_path, *projects):
    vault = settings.set_vault_path(tmp_path / 'vault')
    for project in projects:
        settings.add_project(project)
    return vault


def add(service, content='First title', project='p', **kwargs):
    return service.add_memory([1.0, 0.0], content, project, 'decision', **kwargs)


def page(vault, memory_id, project='p'):
    return next((project_dir(vault, project) / 'memories').glob(f'*-{memory_id[:8]}.md'))


def test_nothing_written_without_vault_or_opt_in(tmp_path, service, mirror, monkeypatch):
    add(service)
    vault = configure(tmp_path)
    add(service)
    assert not list(vault.rglob('*.md'))
    assert mirror.sync_project('p').written == 0


def test_add_memory_writes_page_project_and_log_when_mirrored(tmp_path, service, mirror):
    vault = configure(tmp_path, 'p')
    memory_id = add(service)
    assert 'First title' in page(vault, memory_id).read_text()
    for filename in ('p.md', 'log.md'):
        assert page(vault, memory_id).stem in (project_dir(vault, 'p') / filename).read_text()
    assert not (project_dir(vault, 'p') / 'files.md').exists()


def test_edit_keeps_stem_and_refreshes_neighbor_aliases(tmp_path, service, mirror):
    vault = configure(tmp_path, 'p')
    first, second = add(service), add(service, 'Neighbor')
    service.link_memories(second, 'supports', first)
    before = page(vault, first)
    service.edit_memory(first, 'Changed heading\nNew body', [1.0, 0.0])
    assert page(vault, first) == before
    assert 'New body' in before.read_text()
    for path in (page(vault, second), project_dir(vault, 'p') / 'p.md', project_dir(vault, 'p') / 'log.md'):
        assert f'{before.stem}|Changed heading]]' in path.read_text()
    mirror.sync_project('p')
    assert page(vault, first) == before


def test_supersede_updates_both_pages(tmp_path, service, mirror):
    vault = configure(tmp_path, 'p')
    first = add(service)
    second = add(service, 'Replacement', supersedes=first)
    assert f'Replaced by [[Chronicle/p/memories/{page(vault, second).stem}|' in page(vault, first).read_text()
    assert page(vault, first).stem in page(vault, second).read_text()


def test_link_across_two_mirrored_projects_updates_both(tmp_path, service, mirror):
    vault = configure(tmp_path, 'p', 'q')
    first, second = add(service), add(service, 'Other', 'q')
    service.link_memories(first, 'supports', second)
    assert page(vault, second, 'q').stem in page(vault, first).read_text()
    assert page(vault, first).stem in page(vault, second, 'q').read_text()
    service.edit_memory(second, 'Renamed other', [1.0, 0.0])
    assert '|Renamed other]]' in page(vault, first).read_text()


def test_link_to_unmirrored_project_leaks_nothing(tmp_path, service, mirror, monkeypatch):
    vault = configure(tmp_path, 'p')
    secret, public = add(service, 'TOP SECRET CONTENT', 'private'), add(service)
    original = service.repository.get_by_ids
    def guarded(ids):
        ids = list(ids)
        assert secret not in ids, 'private content must never be loaded'
        return original(ids)
    monkeypatch.setattr(service.repository, 'get_by_ids', guarded)
    service.link_memories(public, 'supports', secret)
    mirror.sync_project('p')
    text = '\n'.join(path.read_text() for path in vault.rglob('*.md'))
    assert '(in project private, not mirrored)' in text
    assert 'TOP SECRET' not in text
    assert not project_dir(vault, 'private').exists()


def test_vault_folder_removed_does_not_break_memory_add(tmp_path, service, mirror):
    vault = configure(tmp_path, 'p')
    shutil.rmtree(vault)
    memory_id = add(service)
    assert service.repository.get(memory_id) is not None
    assert mirror.status()['last_error']
    from chronicle.vault.mirror import VaultMirror
    assert VaultMirror(service).status()['last_error']
    assert not vault.exists()


def test_sync_is_idempotent_and_prunes_orphans(tmp_path, service, mirror):
    vault = configure(tmp_path, 'p')
    memory_id = add(service)
    first = mirror.sync_project('p')
    assert first.written >= 2
    folder = project_dir(vault, 'p')
    orphan = folder / 'memories' / 'orphan.md'
    orphan.write_text('---\ngenerated_by: "chronicle"\nchronicle_id: "absent"\n---\n')
    user = folder / 'user.md'
    user.write_text('keep me')
    topic = folder / 'topics' / 'future.md'
    topic.parent.mkdir()
    topic.write_text(orphan.read_text())
    result = mirror.sync_project('p')
    assert result.written == 0 and result.deleted == 1
    assert str(user) in result.skipped
    assert user.read_text() == 'keep me' and topic.exists() and page(vault, memory_id).exists()
    again = mirror.sync_project('p')
    assert again.written == again.deleted == 0
    from chronicle.vault.mirror import VaultMirror
    status = VaultMirror(service).status()
    assert status['last_sync']['p']
    assert status['projects']['p'] >= 4
    assert str(user) in status['skipped_user_files']
    assert json.loads((tmp_path / 'state' / 'vault-status.json').read_text())['last_sync']['p']


def test_remove_project_deletes_only_marked_files(tmp_path, service, mirror):
    vault = configure(tmp_path, 'p', 'q')
    add(service)
    other = add(service, 'Other', 'q')
    mirror.sync_project('p')
    user = project_dir(vault, 'p') / 'user.md'
    user.write_text('mine')
    assert mirror.remove_project('p') == 4
    assert user.read_text() == 'mine'
    assert page(vault, other, 'q').exists()
    assert 'p' not in settings.vault_projects()
    assert str(user) in mirror.status()['skipped_user_files']


def test_observer_failure_is_isolated(service, capsys):
    calls = []
    def broken(ids):
        raise RuntimeError('observer unavailable')
    service.observers.extend([broken, calls.append])
    memory_id = add(service)
    assert calls == [[memory_id]]
    assert 'observer unavailable' in capsys.readouterr().err


@pytest.mark.parametrize('operation', ['confirm', 'wrong', 'retract', 'document'])
def test_remaining_mutations_refresh(tmp_path, service, mirror, operation):
    vault = configure(tmp_path, 'p')
    memory_id = add(service)
    if operation == 'document':
        memory_id = service.set_document([], 'Overview updated', 'p', 'p', 'overview')
        assert 'Overview updated' in (project_dir(vault, 'p') / 'p.md').read_text()
    else:
        {'confirm': service.confirm_memory, 'wrong': service.mark_wrong, 'retract': service.retract_memory}[operation](memory_id)
        expected = {'confirm': 'confidence: 1.0', 'wrong': 'Marked wrong', 'retract': 'Retracted'}[operation]
        assert expected in page(vault, memory_id).read_text()


@pytest.mark.parametrize('operation', ['merge', 'split'])
def test_compound_mutations_notify_once_with_all_ids(service, operation):
    first, second = add(service), add(service, 'Second')
    calls = []
    service.observers.append(calls.append)
    if operation == 'merge':
        new = [service.merge_memories([], 'Merged', 'p', 'decision', [first, second])]
        expected = {first, second, *new}
    else:
        new = service.split_memory(first, [([], 'A', 'decision'), ([], 'B', 'fact')])
        expected = {first, *new}
    assert len(calls) == 1
    assert set(calls[0]) == expected


def test_similarity_links_only_when_enabled(tmp_path, service, mirror, monkeypatch):
    from chronicle import config

    vault = configure(tmp_path, 'p', 'q')
    first, second = add(service), add(service, 'Similar')
    add(service, 'Other project', 'q')
    mirror.sync_project('p')
    assert 'similar:' not in page(vault, first).read_text()
    data = config.read_config()
    data['vault_similarity_links'] = True
    config.write_config(data)
    mirror.sync_project('p')
    before = page(vault, first).read_text()
    assert f'similar: [[Chronicle/p/memories/{page(vault, second).stem}|' in before
    assert 'Chronicle/q/' not in before
    service.edit_memory(first, 'Changed', [0.0, 1.0])
    assert 'similar:' in page(vault, first).read_text()
    mirror.sync_project('p')
    assert 'similar:' not in page(vault, first).read_text()
    monkeypatch.setenv('CHRONICLE_SEMANTIC', '0')
    mirror.sync_project('p')
    assert 'similar:' not in page(vault, second).read_text()


def test_runtime_wires_mirror(tmp_path, service):
    from chronicle.core.runtime import create_runtime

    vault = configure(tmp_path, 'p')
    runtime = create_runtime(service.vector_index, service.repository.database)
    memory_id = add(runtime)
    assert page(vault, memory_id).exists()


def test_inbound_relations_are_project_scoped(service):
    target = add(service)
    first, second = add(service, project='q'), add(service, project='private')
    service.link_memories(first, 'supports', target)
    service.link_memories(second, 'disputes', target)
    assert service.repository.inbound_relations('q', {target}) == [(first, 'supports', target)]
    assert service.repository.inbound_relations('q', set()) == []


def test_live_refresh_scans_inbound_once_per_opted_in_project(tmp_path, service, mirror, monkeypatch):
    configure(tmp_path, 'p', 'q')
    first, second = add(service), add(service, 'Other', 'q')
    original = service.repository.inbound_relations
    calls = []
    def tracked(project, ids):
        calls.append(project)
        return original(project, ids)
    monkeypatch.setattr(service.repository, 'inbound_relations', tracked)
    service.link_memories(first, 'supports', second)
    assert sorted(calls) == ['p', 'q']


def test_memory_directory_symlink_cannot_write_another_project(tmp_path, service, mirror):
    vault = configure(tmp_path, 'p')
    other = project_dir(vault, 'private') / 'memories'
    other.mkdir(parents=True)
    folder = project_dir(vault, 'p')
    folder.mkdir()
    (folder / 'memories').symlink_to(other, target_is_directory=True)
    memory_id = add(service)
    assert service.repository.get(memory_id)
    assert not list(other.iterdir())
    assert mirror.status()['last_error']


def test_sync_reports_unmarked_generated_path_collision(tmp_path, service, mirror):
    vault = configure(tmp_path, 'p')
    folder = project_dir(vault, 'p')
    folder.mkdir()
    user = folder / 'p.md'
    user.write_text('user project page')
    add(service)
    result = mirror.sync_project('p')
    assert user.read_text() == 'user project page'
    assert str(user) in result.skipped


def test_stable_stem_confirms_full_frontmatter_id(tmp_path, service, mirror):
    vault = configure(tmp_path, 'p')
    memory_id = add(service)
    original = page(vault, memory_id)
    impostor = original.parent / f'aaa-{memory_id[:8]}.md'
    impostor.write_text('---\ngenerated_by: "chronicle"\nchronicle_id: "different"\n---\n')
    service.edit_memory(memory_id, 'New title', [])
    assert 'New title' in original.read_text()
    assert 'New title' not in impostor.read_text()
    mirror.sync_project('p')
    assert original.exists() and not impostor.exists()


def test_no_db_reads_without_configured_vault(service, mirror, monkeypatch):
    from sqlalchemy import event

    def fail(*args):
        pytest.fail('unconfigured mirror must not query SQLite')
    engine = service.repository.database.engine
    event.listen(engine, 'before_cursor_execute', fail)
    try:
        mirror.on_memories_changed(['any'])
    finally:
        event.remove(engine, 'before_cursor_execute', fail)


def test_live_refresh_does_not_copy_content_as_similarity(tmp_path, service, mirror):
    vault = configure(tmp_path, 'p')
    memory_id = add(service, 'Title\nsimilar: user prose')
    service.confirm_memory(memory_id)
    assert page(vault, memory_id).read_text().count('similar: user prose') == 1


@pytest.mark.parametrize("write_first", [False, True])
def test_projection_reads_headers_only_for_written_unique_candidates(tmp_path, service, mirror, monkeypatch, write_first):
    from chronicle.vault import projection

    vault = configure(tmp_path, 'p')
    # Populate once without invoking the live mirror for each setup memory.
    service.observers.clear()
    ids = [add(service, f'Memory {index}') for index in range(20)]
    mirror.sync_project('p')
    original = projection.page_id
    scan = projection.os.scandir
    reads, scans = [], []
    def tracked_scan(path):
        scans.append(path)
        return scan(path)
    def tracked(path):
        reads.append(path)
        return original(path)
    monkeypatch.setattr(projection, 'page_id', tracked)
    monkeypatch.setattr(projection.os, 'scandir', tracked_scan)
    result = projection.Projection(service, vault, ['p'], ['p'], write_ids={ids[0]} if write_first else set())
    assert scans == [project_dir(vault, 'p') / 'memories']
    assert reads == ([page(vault, ids[0])] if write_first else [])
    assert len(result.links) == 20


def test_sync_prunes_duplicate_at_noncanonical_path(tmp_path, service, mirror):
    vault = configure(tmp_path, 'p')
    memory_id = add(service)
    canonical = page(vault, memory_id)
    duplicate = project_dir(vault, 'p') / 'duplicate.md'
    duplicate.write_text(canonical.read_text())
    result = mirror.sync_project('p')
    assert canonical.exists() and not duplicate.exists()
    assert result.deleted == 1
    assert mirror.sync_project('p').deleted == 0


def test_remove_project_opts_out_when_vault_unavailable(tmp_path, service, mirror):
    vault = configure(tmp_path, 'p')
    add(service)
    shutil.rmtree(vault)
    with pytest.raises(RuntimeError, match='generated files could not be deleted'):
        mirror.remove_project('p')
    assert 'p' not in settings.vault_projects()
    assert mirror.status()['last_error']
