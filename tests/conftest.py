import subprocess
from pathlib import Path

import pytest

from chronicle.core.repository import MemoryRepository
from chronicle.core.service import MemoryService
from chronicle.storage.database import Database

from fake_vector import FakeVectorIndex


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    from chronicle import config

    monkeypatch.setenv("CHRONICLE_STATE_DIR", str(tmp_path / "state"))
    path = tmp_path / "config.json"
    monkeypatch.setenv("CHRONICLE_CONFIG_PATH", str(path))
    monkeypatch.setattr(config, "CONFIG_PATH", path)


@pytest.fixture
def service(tmp_path, isolate_config):
    database = Database(f"sqlite:///{tmp_path / 'chronicle.db'}")
    return MemoryService(MemoryRepository(database), FakeVectorIndex())


@pytest.fixture(autouse=True)
def isolate_server_runtime(service, monkeypatch):
    from chronicle import config, server
    from chronicle.core import runtime

    monkeypatch.setenv("CHRONICLE_PROJECT", "chronicle-test")
    monkeypatch.setenv("CHRONICLE_SEMANTIC", "1")
    monkeypatch.setattr(server, "_service", service, raising=False)
    monkeypatch.setattr(runtime, "_runtime", service)
    monkeypatch.setattr(config, "SQLITE_PATH", service.repository.database.path)


def git_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    return path


@pytest.fixture(autouse=True)
def isolate_project_resolution(tmp_path, monkeypatch):
    from chronicle import project_resolution

    monkeypatch.setenv("CHRONICLE_REGISTRY_PATH", str(tmp_path / "projects.json"))
    project_resolution.take_registration_notice()
    yield
    project_resolution.take_registration_notice()
