import pytest

from sqlalchemy import select, text, update

from mnemo.core.repository import MemoryRepository
from mnemo.core.service import MemoryService
from mnemo.storage.database import Database
from mnemo.storage.models import Episode, Memory

from fake_vector import FakeVectorIndex


def make_service(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'mnemo.db'}")
    return MemoryService(MemoryRepository(database), FakeVectorIndex())


def test_database_bootstrap_includes_memory_fts(service):
    with service.repository.session_factory() as session:
        assert session.scalar(
            text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'memory_fts'")
        ) == 1


def test_add_memory_writes_authoritative_row_and_vector(tmp_path):
    service = make_service(tmp_path)

    memory_id = service.add_memory([1.0, 0.0], "SQLite is canonical", "p", "architecture")

    with service.repository.session_factory() as session:
        row = session.scalar(select(Memory).where(Memory.id == memory_id))
    assert row is not None
    assert row.content == "SQLite is canonical"
    assert service.vector_index.points[memory_id]["metadata"] == {"project": "p", "type": "architecture"}


def test_provenance_fields_round_trip_through_latest_and_search(tmp_path):
    service = make_service(tmp_path)

    memory_id = service.add_memory(
        [1.0],
        "manual provenance memory",
        "p",
        "note",
        confidence=0.8,
        extraction_method="manual",
    )

    latest = service.get_latest("p", "note")
    search_result = service.search([1.0], "p", query_text="manual provenance memory", k=1)[0]

    assert latest["id"] == memory_id
    assert latest["confidence"] == 0.8
    assert latest["extraction_method"] == "manual"
    assert search_result["confidence"] == 0.8
    assert search_result["extraction_method"] == "manual"


def test_document_provenance_fields_round_trip_through_get_document(tmp_path):
    service = make_service(tmp_path)

    service.set_document(
        [1.0],
        "document provenance",
        "p",
        "provenance-doc",
        "note",
        confidence=0.8,
        extraction_method="manual",
    )

    document = service.get_document("p", "provenance-doc")

    assert document["confidence"] == 0.8
    assert document["extraction_method"] == "manual"


def test_serialization_includes_episode_id_and_title(tmp_path):
    service = make_service(tmp_path)
    episode_id = "episode-1"

    with service.repository.session_factory() as session:
        session.add(Episode(id=episode_id, project="p", title="Manual import"))
        session.commit()

    memory_id = service.add_memory([1.0], "episode memory", "p", "note")
    with service.repository.session_factory() as session:
        session.execute(update(Memory).where(Memory.id == memory_id).values(episode_id=episode_id))
        session.commit()

    serialized = service.get_latest("p", "note")

    assert serialized["episode_id"] == episode_id
    assert serialized["episode_title"] == "Manual import"


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


def test_exact_text_match_surfaces_through_lexical_search(tmp_path):
    service = make_service(tmp_path)
    service.add_memory([0.0], "unrelated vector result", "p", "note")
    lexical_id = service.add_memory([1.0], "unique lexical phrase", "p", "note")

    results = service.search([1.0], "p", query_text="unique lexical phrase", k=1)

    assert results[0]["id"] == lexical_id


def test_fts_updates_after_insert_and_document_overwrite(service):
    memory_id = service.add_memory([1.0], "inserted lexical text", "p", "note")

    assert [row.id for row in service.repository.lexical("p", "inserted lexical text", None, 5, False)] == [
        memory_id
    ]
    with service.repository.session_factory() as session:
        assert session.scalar(
            text("SELECT content FROM memory_fts WHERE memory_id = :memory_id"),
            {"memory_id": memory_id},
        ) == "inserted lexical text"

    document_id = service.set_document([1.0], "document version one", "p", "doc", "note")
    service.set_document([1.0], "document version two", "p", "doc", "note")

    assert service.repository.lexical("p", "document version one", None, 5, False) == []
    assert [row.id for row in service.repository.lexical("p", "document version two", None, 5, False)] == [
        document_id
    ]
    with service.repository.session_factory() as session:
        assert session.scalar(
            text("SELECT content FROM memory_fts WHERE memory_id = :memory_id"),
            {"memory_id": document_id},
        ) == "document version two"


def test_fts_query_special_characters_do_not_crash(service):
    service.add_memory([1.0], "ordinary content", "p", "note")

    assert service.repository.lexical("p", '"*-', None, 5, False) == []


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("search", ([1.0], "")),
        ("get_latest", ("", "note")),
        ("get_recent", ("", "note")),
        ("get_document", ("", "slug")),
        ("add_memory", ([1.0], "content", "", "note")),
        ("set_document", ([1.0], "content", "", "slug", "note")),
    ],
)
def test_project_scoped_service_methods_reject_empty_project(service, method, args):
    with pytest.raises(ValueError, match="project must not be empty"):
        getattr(service, method)(*args)


def test_explicit_global_paths_remain_unfiltered(service):
    project_id = service.add_memory([1.0], "project scope probe", "p", "note")
    other_project_id = service.add_memory([1.0], "other scope probe", "q", "note")

    search_ids = {
        row["id"] for row in service.search_global([1.0], query_text="scope probe", k=5)
    }
    vector_ids = {row["id"] for row in service.get_all_with_vectors()}

    assert search_ids == {project_id, other_project_id}
    assert vector_ids == {project_id, other_project_id}


def test_project_scoped_search_returns_only_requested_project(service):
    project_id = service.add_memory([1.0], "project scope probe", "p", "note")
    service.add_memory([1.0], "other scope probe", "q", "note")

    results = service.search([1.0], "p", query_text="scope probe", k=5)

    assert {row["id"] for row in results} == {project_id}
