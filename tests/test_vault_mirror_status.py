"""Mirror status survives process boundaries and covers every project in a sync."""
import json
import subprocess
import sys

import pytest

from chronicle.vault import catalog, settings
from chronicle.vault.mirror import VaultMirror


def test_status_is_readable_by_another_process(tmp_path, service):
    settings.set_vault_path(tmp_path / 'vault')
    settings.add_project('p')
    service.add_memory([], 'Memory', 'p', 'decision')
    mirror = VaultMirror(service)
    mirror.sync_project('p')
    result = subprocess.run(
        [sys.executable, '-c',
         'import json; from chronicle.vault.mirror import VaultMirror; '
         'print(json.dumps(VaultMirror(None).status()))'],
        capture_output=True, text=True, check=True,
    )
    status = json.loads(result.stdout)
    assert status['last_sync'] == mirror.status()['last_sync']
    assert status['projects']['p'] == 4


def test_sync_all_keeps_errors_and_skipped_files_from_earlier_projects(tmp_path, service, monkeypatch):
    vault = settings.set_vault_path(tmp_path / 'vault')
    for project in ('p', 'q'):
        settings.add_project(project)
        service.add_memory([], 'Memory', project, 'decision')
    user = vault / "Chronicle/p/p.md"
    user.parent.mkdir(parents=True)
    user.write_text("user page")
    original = catalog.list_files
    def unavailable(project):
        if project == 'p':
            raise OSError('catalog unavailable')
        return original(project)
    monkeypatch.setattr(catalog, 'list_files', unavailable)
    mirror = VaultMirror(service)
    results = mirror.sync_all()
    assert [result.project for result in results] == ['p', 'q']
    assert (vault / 'Chronicle/q/files.md').exists()
    assert mirror.status()['last_error'] == 'catalog unavailable'
    assert str(user) in mirror.status()['skipped_user_files']


@pytest.mark.parametrize("failed", [False, True])
def test_live_refresh_preserves_sync_diagnostics(tmp_path, service, failed):
    from chronicle.vault.state import record_status

    vault = settings.set_vault_path(tmp_path / 'vault')
    settings.add_project('p')
    mirror = VaultMirror(service)
    service.observers.append(mirror.on_memories_changed)
    user = vault / 'Chronicle/p/p.md'
    user.parent.mkdir(parents=True)
    user.write_text('user page')
    mirror.sync_project('p')
    extra = user.parent / 'user.md'
    extra.write_text('another user note')
    mirror.sync_project('p')
    before = mirror.status()
    record_status(skipped=before['skipped_user_files'], error=OSError('previous sync failure'))
    if failed:
        import shutil
        shutil.rmtree(vault)
    service.add_memory([], 'New memory', 'p', 'decision')
    after = mirror.status()
    assert after['last_sync'] == before['last_sync']
    assert after['skipped_user_files'] == before['skipped_user_files']
    if failed:
        assert 'vault folder unavailable' in after['last_error']
    else:
        assert after['last_error'] == 'previous sync failure'
        assert after['last_refresh']['p']


def test_empty_successful_sync_all_clears_stale_error(service):
    from chronicle.vault.state import record_status

    record_status(error=OSError('old run'))
    mirror = VaultMirror(service)
    assert mirror.sync_all() == []
    assert mirror.status()['last_error'] is None


def test_mirror_for_reuses_wired_observer_or_constructs(service):
    from chronicle.vault.mirror import mirror_for

    fallback = mirror_for(service)
    assert isinstance(fallback, VaultMirror)
    assert fallback.service is service
    wired = VaultMirror(service)
    service.observers.extend([lambda ids: None, wired.on_memories_changed])
    assert mirror_for(service) is wired


def test_core_add_validates_and_syncs(service, tmp_path):
    from chronicle import registry

    mirror = VaultMirror(service)
    with pytest.raises(ValueError, match='no vault configured'):
        mirror.add_project('p')
    settings.set_vault_path(tmp_path / 'vault')
    with pytest.raises(ValueError, match='project does not exist: typo'):
        mirror.add_project('typo')
    assert settings.vault_projects() == []
    service.add_memory([], 'Memory', 'p', 'note')
    assert mirror.add_project('p').written == 5
    assert mirror.add_project('p').unchanged == 5
    registry.register(tmp_path / 'docs', 'registered')
    assert mirror.add_project('registered').written == 4
    assert settings.vault_projects() == ['p', 'registered']


def test_sync_result_retains_own_error_when_status_write_fails(service, tmp_path, monkeypatch):
    import shutil
    from chronicle.vault import mirror as module

    vault = settings.set_vault_path(tmp_path / 'vault')
    settings.add_project('p')
    shutil.rmtree(vault)
    monkeypatch.setattr(module, 'record_status', lambda *args, **kwargs: None)
    result = VaultMirror(service).sync_project('p')
    assert 'unavailable' in result.error
    with pytest.raises(RuntimeError, match='unavailable'):
        result.raise_for_error()


def test_successful_sync_all_ignores_raced_shared_diagnostics(service, tmp_path, monkeypatch):
    from chronicle.vault import mirror as module

    settings.set_vault_path(tmp_path / 'vault')
    settings.add_project('p')
    original = module.record_status

    def raced_status(*args, **kwargs):
        original(*args, **kwargs)
        original(error=OSError('concurrent refresh failure'))

    monkeypatch.setattr(module, 'record_status', raced_status)
    results = VaultMirror(service).sync_all()
    assert len(results) == 1
    assert results[0].error is None
    results[0].raise_for_error()
