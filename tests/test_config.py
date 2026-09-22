from pathlib import Path

import pytest

from mnemo import config, registry


def test_get_project_reads_env(monkeypatch):
    monkeypatch.setenv("MNEMO_PROJECT", "villenca")
    assert config.get_project() == "villenca"


def test_get_project_raises_when_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("MNEMO_PROJECT", raising=False)
    monkeypatch.setenv("MNEMO_REGISTRY_PATH", str(tmp_path / "projects.json"))
    with pytest.raises(RuntimeError):
        config.get_project()


def test_get_project_raises_when_blank(monkeypatch, tmp_path):
    monkeypatch.setenv("MNEMO_PROJECT", "   ")
    monkeypatch.setenv("MNEMO_REGISTRY_PATH", str(tmp_path / "projects.json"))
    with pytest.raises(RuntimeError):
        config.get_project()


def test_validate_type_accepts_known_types():
    for known in ("decision", "architecture", "bug", "todo", "note", "checkpoint", "overview"):
        config.validate_type(known)  # must not raise


def test_validate_type_rejects_unknown():
    with pytest.raises(ValueError):
        config.validate_type("nonsense")


def test_validate_status_accepts_known_statuses():
    for known in ("active", "resolved", "superseded"):
        config.validate_status(known)  # must not raise


def test_validate_status_rejects_unknown():
    with pytest.raises(ValueError):
        config.validate_status("nonsense")


def test_validate_relation_type_accepts_known_types():
    for known in ("related_to", "supersedes", "caused_by", "blocked_by", "implements"):
        config.validate_relation_type(known)  # must not raise


def test_validate_relation_type_rejects_unknown():
    with pytest.raises(ValueError):
        config.validate_relation_type("nonsense")


def test_get_project_falls_back_to_registry(monkeypatch, tmp_path):
    monkeypatch.delenv("MNEMO_PROJECT", raising=False)
    monkeypatch.setenv("MNEMO_REGISTRY_PATH", str(tmp_path / "projects.json"))
    registry.register(Path.cwd(), "registry-project")
    assert config.get_project() == "registry-project"


def test_get_project_env_wins_over_registry(monkeypatch, tmp_path):
    monkeypatch.setenv("MNEMO_PROJECT", "env-project")
    monkeypatch.setenv("MNEMO_REGISTRY_PATH", str(tmp_path / "projects.json"))
    registry.register(Path.cwd(), "registry-project")
    assert config.get_project() == "env-project"


def test_get_project_raises_when_neither_env_nor_registry(monkeypatch, tmp_path):
    monkeypatch.delenv("MNEMO_PROJECT", raising=False)
    monkeypatch.setenv("MNEMO_REGISTRY_PATH", str(tmp_path / "projects.json"))
    with pytest.raises(RuntimeError):
        config.get_project()


def test_get_project_raises_runtime_error_on_corrupt_registry(monkeypatch, tmp_path):
    monkeypatch.delenv("MNEMO_PROJECT", raising=False)
    registry_path = tmp_path / "projects.json"
    registry_path.write_text("{not valid json")
    monkeypatch.setenv("MNEMO_REGISTRY_PATH", str(registry_path))
    with pytest.raises(RuntimeError):
        config.get_project()
