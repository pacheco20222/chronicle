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
