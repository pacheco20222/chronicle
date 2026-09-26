import pytest

from chronicle.core.repository import MemoryRepository
from chronicle.core.service import MemoryService
from chronicle.storage.database import Database

from fake_vector import FakeVectorIndex


@pytest.fixture
def service(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'chronicle.db'}")
    return MemoryService(MemoryRepository(database), FakeVectorIndex())


@pytest.fixture(autouse=True)
def isolate_server_runtime(service, monkeypatch):
    from chronicle import config, server
    from chronicle.core import runtime

    monkeypatch.setenv("CHRONICLE_PROJECT", "chronicle-test")
    monkeypatch.setattr(server, "_service", service, raising=False)
    monkeypatch.setattr(runtime, "_runtime", service)
    monkeypatch.setattr(config, "SQLITE_PATH", service.repository.database.path)
