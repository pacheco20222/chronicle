import pytest

from chronicle import cli, scope_cli


def _use_service(monkeypatch, service):
    monkeypatch.setattr(scope_cli, "get_runtime", lambda: service)


def test_scope_create_reports_created_ancestors(monkeypatch, service, capsys):
    _use_service(monkeypatch, service)

    scope_cli.main(["create", "personal/chronicle"])

    output = capsys.readouterr().out
    assert "personal" in output
    assert "personal/chronicle" in output
    assert service.repository.get_scope_by_path("personal/chronicle") is not None


def test_scope_list_prints_tree_without_prefix(monkeypatch, service, capsys):
    _use_service(monkeypatch, service)
    service.repository.get_or_create_scope("personal/chronicle")
    service.repository.get_or_create_scope("personal/heliofi/backend")

    scope_cli.main(["list"])

    assert capsys.readouterr().out.splitlines() == [
        "personal",
        "  personal/chronicle",
        "  personal/heliofi",
        "    personal/heliofi/backend",
    ]


def test_scope_list_filters_prefix(monkeypatch, service, capsys):
    _use_service(monkeypatch, service)
    service.repository.get_or_create_scope("personal/chronicle")
    service.repository.get_or_create_scope("personal/heliofi/backend")
    service.repository.get_or_create_scope("work/notes")

    scope_cli.main(["list", "--prefix", "personal/heliofi"])

    assert capsys.readouterr().out.splitlines() == [
        "  personal/heliofi",
        "    personal/heliofi/backend",
    ]


def test_scope_move_to_parent_prints_new_path(monkeypatch, service, capsys):
    _use_service(monkeypatch, service)
    service.repository.get_or_create_scope("personal/chronicle")
    service.repository.get_or_create_scope("work")

    scope_cli.main(["move", "personal/chronicle", "--to", "work"])

    assert "work/chronicle" in capsys.readouterr().out
    assert service.repository.get_scope_by_path("work/chronicle") is not None


def test_scope_move_without_parent_moves_to_root(monkeypatch, service, capsys):
    _use_service(monkeypatch, service)
    service.repository.get_or_create_scope("personal/chronicle")

    scope_cli.main(["move", "personal/chronicle"])

    assert "chronicle" in capsys.readouterr().out
    assert service.repository.get_scope_by_path("chronicle") is not None


def test_scope_move_missing_path_exits_with_error(monkeypatch, service, capsys):
    _use_service(monkeypatch, service)

    with pytest.raises(SystemExit) as error:
        scope_cli.main(["move", "missing"])

    assert error.value.code == 1
    assert "no scope found at path 'missing'" in capsys.readouterr().err


def test_cli_dispatches_scope_subcommand(monkeypatch):
    called = {}

    def fake_scope_main(argv):
        called["argv"] = argv

    monkeypatch.setattr(scope_cli, "main", fake_scope_main)
    monkeypatch.setattr(cli.sys, "argv", ["chronicle", "scope", "list", "--prefix", "work"])

    cli.main()

    assert called["argv"] == ["list", "--prefix", "work"]
