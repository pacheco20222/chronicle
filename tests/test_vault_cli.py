from pathlib import Path

import pytest

from chronicle import cli, registry
from chronicle.vault import settings
from chronicle.vault.mirror import VaultMirror


def invoke(monkeypatch, *args):
    monkeypatch.setattr('sys.argv', ['chronicle', 'vault', *args])
    cli.main()


def test_cli_round_trip(service, tmp_path, monkeypatch, capsys):
    service.observers.append(VaultMirror(service).on_memories_changed)
    service.add_memory([], 'A decision', 'demo', 'decision')
    vault = tmp_path / 'vault'
    invoke(monkeypatch, 'set', str(vault))
    assert str(vault) in capsys.readouterr().out
    invoke(monkeypatch, 'add', 'demo')
    assert capsys.readouterr().out == 'demo: 5 written, 0 unchanged, 0 deleted\n'
    service.add_memory([], 'Another note', 'demo', 'note')
    invoke(monkeypatch, 'sync', 'demo')
    assert capsys.readouterr().out == 'demo: 0 written, 6 unchanged, 0 deleted\n'
    invoke(monkeypatch, 'sync')
    assert capsys.readouterr().out == 'demo: 0 written, 6 unchanged, 0 deleted\n'
    user = vault / 'Chronicle/demo/mine.md'
    user.write_text('Keep me')
    invoke(monkeypatch, 'sync')
    assert capsys.readouterr().out == 'demo: 0 written, 6 unchanged, 0 deleted, 1 skipped\n'
    invoke(monkeypatch, 'status')
    output = capsys.readouterr().out
    for value in (str(vault), 'demo: 5 pages', 'last_sync:', 'last_refresh:', 'last_error:', str(user)):
        assert value in output
    invoke(monkeypatch, 'remove', 'demo')
    assert '5 deleted' in capsys.readouterr().out
    assert user.read_text() == 'Keep me'
    assert settings.vault_projects() == []
    assert not list((vault / 'Chronicle/demo').glob('memories/*.md'))


@pytest.mark.parametrize('path', [str(Path.home()), '/'])
def test_set_refuses_home_and_root(path, monkeypatch, capsys):
    with pytest.raises(SystemExit) as error:
        invoke(monkeypatch, 'set', path)
    assert error.value.code == 1
    assert 'home/root' in capsys.readouterr().err


def test_add_refuses_unconfigured_vault_and_unknown_project(service, tmp_path, monkeypatch, capsys):
    service.add_memory([], 'x', 'demo', 'note')
    with pytest.raises(SystemExit) as error:
        invoke(monkeypatch, 'add', 'demo')
    assert error.value.code == 1
    assert 'vault' in capsys.readouterr().err
    settings.set_vault_path(tmp_path / 'vault')
    with pytest.raises(SystemExit) as error:
        invoke(monkeypatch, 'add', 'typo')
    assert error.value.code == 1
    assert 'typo' in capsys.readouterr().err
    assert settings.vault_projects() == []


def test_add_accepts_registry_only_project(tmp_path, monkeypatch):
    registry.register(tmp_path / 'docs', 'registered')
    settings.set_vault_path(tmp_path / 'vault')
    invoke(monkeypatch, 'add', 'registered')
    assert settings.vault_projects() == ['registered']


def test_sync_reports_core_failure(service, tmp_path, monkeypatch, capsys):
    vault = settings.set_vault_path(tmp_path / 'vault')
    settings.add_project('demo')
    (vault / 'Chronicle').rmdir()
    vault.rmdir()
    with pytest.raises(SystemExit) as error:
        invoke(monkeypatch, 'sync')
    assert error.value.code == 1
    assert 'unavailable' in capsys.readouterr().err


def test_cli_sync_refuses_non_opted_in_project(tmp_path, monkeypatch, capsys):
    settings.set_vault_path(tmp_path / 'vault')
    with pytest.raises(SystemExit) as error:
        invoke(monkeypatch, 'sync', 'unknown')
    assert error.value.code == 1
    assert 'not opted in' in capsys.readouterr().err
    assert settings.vault_projects() == []


@pytest.mark.parametrize('command', [('sync', 'demo'), ('sync',), ('add', 'demo'), ('remove', 'demo')])
def test_cli_success_ignores_stale_status(service, tmp_path, monkeypatch, command):
    service.add_memory([], 'Memory', 'demo', 'note')
    settings.set_vault_path(tmp_path / 'vault')
    settings.add_project('demo')
    # Simulate a refresh error written between this run finishing and status inspection.
    monkeypatch.setattr(VaultMirror, 'status', lambda self: {'last_error': 'stale refresh error'})
    invoke(monkeypatch, *command)
