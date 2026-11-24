import threading

import anyio
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from chronicle import refresh, registry, server
from chronicle.vault import settings
from chronicle.vault.mirror import VaultMirror


@pytest.fixture(autouse=True)
def vault_runtime(service, monkeypatch):
    service.observers.append(VaultMirror(service).on_memories_changed)
    monkeypatch.setattr(refresh, '_state', dict(refresh._IDLE))
    yield
    for thread in threading.enumerate():
        if thread.name == 'chronicle-refresh':
            thread.join(timeout=5)


def test_vault_tool_round_trip(service, tmp_path):
    service.add_memory([], 'A note', 'demo', 'note')
    vault = settings.set_vault_path(tmp_path / 'vault')

    async def run():
        async with Client(server.mcp) as client:
            added = await client.call_tool('memory_vault_add_project', {'project': 'demo'})
            assert added.data['written'] == 5
            assert len(list((vault / 'Chronicle/demo/memories').glob('*.md'))) == 1
            status = await client.call_tool('memory_vault_status', {})
            assert status.data['projects'] == {'demo': 4}
            again = await client.call_tool('memory_vault_add_project', {'project': 'demo'})
            assert again.data['written'] == 0
            assert again.data['unchanged'] == 5
            removed = await client.call_tool('memory_vault_remove_project', {'project': 'demo'})
            assert removed.data['deleted'] == 4
            assert not (vault / 'Chronicle/demo').exists()
            assert settings.vault_projects() == []

    anyio.run(run)


def test_add_refusals_and_registry_only_project(service, tmp_path):
    service.add_memory([], 'x', 'demo', 'note')

    async def run():
        async with Client(server.mcp) as client:
            with pytest.raises(ToolError, match='vault'):
                await client.call_tool('memory_vault_add_project', {'project': 'demo'})
            settings.set_vault_path(tmp_path / 'vault')
            with pytest.raises(ToolError, match='typo'):
                await client.call_tool('memory_vault_add_project', {'project': 'typo'})
            assert settings.vault_projects() == []
            registry.register(tmp_path / 'docs', 'registered')
            await client.call_tool('memory_vault_add_project', {'project': 'registered'})
            assert settings.vault_projects() == ['registered']

    anyio.run(run)


def test_list_files_filters_and_resolves_scope_without_vault(tmp_path, monkeypatch):
    folder = tmp_path / 'docs'
    folder.mkdir()
    (folder / 'Payments.PDF').write_bytes(b'abc')
    (folder / 'other.txt').write_text('other')
    registry.register(folder, 'demo')
    monkeypatch.setenv('CHRONICLE_PROJECT', 'demo')

    async def run():
        async with Client(server.mcp) as client:
            for args in ({'query': 'PAYMENT'}, {'query': 'PAYMENT', 'scope_path': 'demo'}):
                result = await client.call_tool('memory_list_files', args)
                assert result.data['project'] == 'demo'
                assert result.data['truncated'] is False
                assert len(result.data['files']) == 1
                entry = result.data['files'][0]
                assert entry == {'folder': str(folder), 'path': 'Payments.PDF',
                                 'absolute_path': str(folder / 'Payments.PDF'),
                                 'size': 3, 'modified': entry['modified']}
                assert len(entry['modified']) == 10
            monkeypatch.delenv('CHRONICLE_PROJECT')
            monkeypatch.chdir(tmp_path)
            with pytest.raises(ToolError, match='registered'):
                await client.call_tool('memory_list_files', {})
            explicit = await client.call_tool('memory_list_files', {'scope_path': 'demo'})
            assert len(explicit.data['files']) == 2

    anyio.run(run)


@pytest.mark.parametrize('project,total', [(None, 2), ('first', 1)])
def test_vault_job_progress_busy_and_completion(service, tmp_path, monkeypatch, project, total):
    settings.set_vault_path(tmp_path / 'vault')
    for name in ('first', 'second'):
        service.add_memory([], 'x', name, 'note')
        settings.add_project(name)
    entered, release = threading.Event(), threading.Event()
    original = VaultMirror.sync_project
    progress = []

    def blocked_sync(self, name):
        progress.append(refresh.status())
        entered.set()
        assert release.wait(timeout=5)
        return original(self, name)

    monkeypatch.setattr(VaultMirror, 'sync_project', blocked_sync)
    monkeypatch.setenv('CHRONICLE_SEMANTIC', '0')

    async def run():
        async with Client(server.mcp) as client:
            started = await client.call_tool('memory_vault_sync', {'project': project})
            assert started.data['status'] == 'running'
            assert await anyio.to_thread.run_sync(entered.wait, 5)
            try:
                busy = await client.call_tool('memory_vault_sync', {})
                assert busy.data == {'status': 'running', 'label': 'Syncing vault',
                                     'done': 0, 'total': total, 'error': None}
                monkeypatch.setenv('CHRONICLE_SEMANTIC', '1')
                assert refresh.start(service) == busy.data
            finally:
                release.set()

    anyio.run(run)
    for thread in threading.enumerate():
        if thread.name == 'chronicle-refresh':
            thread.join(timeout=5)
    assert refresh.status() == {'status': 'done', 'label': 'Syncing vault',
                                'done': total, 'total': total, 'error': None}
    assert [item['done'] for item in progress] == list(range(total))


def test_vault_sync_returns_existing_job_snapshot(service, monkeypatch):
    refresh._set(status='running', label='Reading documents', done=2, total=3)
    assert refresh.start_vault_sync(service) == refresh.status()


def test_vault_job_surfaces_core_errors(service, tmp_path):
    vault = settings.set_vault_path(tmp_path / 'vault')
    settings.add_project('demo')
    (vault / 'Chronicle').rmdir()
    vault.rmdir()
    refresh.start_vault_sync(service)
    for thread in threading.enumerate():
        if thread.name == 'chronicle-refresh':
            thread.join(timeout=5)
    assert refresh.status()['status'] == 'error'
    assert 'unavailable' in refresh.status()['error']


def test_add_tool_surfaces_mirror_failure(service, tmp_path):
    service.add_memory([], 'x', 'demo', 'note')
    vault = settings.set_vault_path(tmp_path / 'vault')
    (vault / 'Chronicle').rmdir()
    vault.rmdir()

    async def run():
        async with Client(server.mcp) as client:
            with pytest.raises(ToolError, match='unavailable'):
                await client.call_tool('memory_vault_add_project', {'project': 'demo'})
            status = await client.call_tool('memory_vault_status', {})
            assert 'unavailable' in status.data['last_error']

    anyio.run(run)
