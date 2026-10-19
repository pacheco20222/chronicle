from pathlib import Path

import pytest

from chronicle import register_cli, registry


def test_register_writes_registry_entry(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHRONICLE_REGISTRY_PATH", str(tmp_path / "projects.json"))

    register_cli.main(["--project", "cli-registered-project"])

    assert registry.lookup(Path.cwd()) == "cli-registered-project"
    out = capsys.readouterr().out
    assert "cli-registered-project" in out


def test_register_rejects_empty_project(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHRONICLE_REGISTRY_PATH", str(tmp_path / "projects.json"))
    with pytest.raises(SystemExit):
        register_cli.main(["--project", "   "])
    err = capsys.readouterr().err
    assert "required" in err.lower()


def test_register_accepts_positional_name(tmp_path, monkeypatch):
    monkeypatch.setenv("CHRONICLE_REGISTRY_PATH", str(tmp_path / "projects.json"))
    register_cli.main(["positional-proj"])
    assert registry.lookup(Path.cwd()) == "positional-proj"


def test_register_refuses_to_overwrite_without_force(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHRONICLE_REGISTRY_PATH", str(tmp_path / "projects.json"))
    register_cli.main(["first"])
    with pytest.raises(SystemExit):
        register_cli.main(["second"])
    assert "already registered as project 'first'" in capsys.readouterr().err
    assert registry.lookup(Path.cwd()) == "first"

    register_cli.main(["second", "--force"])
    assert registry.lookup(Path.cwd()) == "second"
