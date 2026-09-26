import pytest

from mnemo.core.repository import MemoryRepository
from mnemo.core.service import MemoryService
from mnemo.storage.database import Database

from fake_vector import FakeVectorIndex


@pytest.fixture
def service(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'mnemo.db'}")
    return MemoryService(MemoryRepository(database), FakeVectorIndex())


@pytest.fixture(autouse=True)
def isolate_server_runtime(service, monkeypatch):
    from mnemo import config, server
    from mnemo.core import runtime

    monkeypatch.setenv("MNEMO_PROJECT", "mnemo-test")
    monkeypatch.setattr(server, "_service", service, raising=False)
    monkeypatch.setattr(runtime, "_runtime", service)
    monkeypatch.setattr(config, "SQLITE_PATH", service.repository.database.path)
