from sqlalchemy import select

from mnemo.core.repository import MemoryRepository
from mnemo.core.service import MemoryService
from mnemo.storage.database import Database
from mnemo.storage.models import Base, Memory

from fake_vector import FakeVectorIndex


def make_service(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'mnemo.db'}")
    Base.metadata.create_all(database.engine)
    return MemoryService(MemoryRepository(database), FakeVectorIndex())


def test_add_memory_writes_authoritative_row_and_vector(tmp_path):
    service = make_service(tmp_path)

    memory_id = service.add_memory([1.0, 0.0], "SQLite is canonical", "p", "architecture")

    with service.repository.session_factory() as session:
        row = session.scalar(select(Memory).where(Memory.id == memory_id))
    assert row is not None
    assert row.content == "SQLite is canonical"
    assert service.vector_index.points[memory_id]["metadata"] == {"project": "p", "type": "architecture"}


def test_search_loads_content_from_sqlite_and_hides_superseded_rows(tmp_path):
    service = make_service(tmp_path)
    old_id = service.add_memory([1.0], "old content", "p", "note")
    new_id = service.add_memory([1.0], "new content", "p", "note", supersedes=old_id)

    results = service.search([1.0], "p", query_text="content", k=5)

    assert [row["id"] for row in results] == [new_id]
    assert results[0]["content"] == "new content"
    assert results[0]["relations"] == [{"type": "supersedes", "target": old_id}]


def test_document_is_replaced_by_project_and_slug(tmp_path):
    service = make_service(tmp_path)

    first_id = service.set_document([1.0], "v1", "p", "overview", "architecture")
    second_id = service.set_document([1.0], "v2", "p", "overview", "architecture")

    assert second_id == first_id
    assert service.get_document("p", "overview")["content"] == "v2"


def test_search_global_and_latest_are_project_aware(tmp_path):
    service = make_service(tmp_path)
    local_id = service.add_memory([1.0], "local", "p", "checkpoint")
    global_id = service.add_memory([1.0], "global", "q", "checkpoint")

    assert service.get_latest("p", "checkpoint")["id"] == local_id
    assert {row["id"] for row in service.search_global([1.0], query_text="", k=5)} == {local_id, global_id}
