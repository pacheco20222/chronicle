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
    assert "empty" in err.lower()
