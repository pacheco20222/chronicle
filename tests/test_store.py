import uuid

import pytest


def test_repository_rows_are_project_and_type_scoped(service):
    note_id = service.add_memory([1.0], "note memory", "p", "note")
    service.add_memory([1.0], "bug memory", "p", "bug")
    service.add_memory([1.0], "other project", "q", "note")

    results = service.search([1.0], "p", type_="note", k=5)

    assert [row["id"] for row in results] == [note_id]


def test_new_memory_sets_valid_at_from_created_at(service):
    memory_id = service.add_memory([1.0], "new memory", "p", "note")

    row = service.repository.get(memory_id)
    serialized = service.get_latest("p", "note")

    assert row.valid_at is not None
    assert row.valid_at == row.created_at
    assert row.invalid_at is None
    assert serialized["valid_at"] is not None
    assert serialized["invalid_at"] is None


def test_superseding_on_add_preserves_history_and_hides_old_memory(service):
    old_id = service.add_memory([1.0], "old fact", "p", "note")
    new_id = service.add_memory([1.0], "new fact", "p", "note", supersedes=old_id)

    old = service.repository.get(old_id)

    assert old is not None
    assert old.status == "superseded"
    assert old.invalid_at is not None
    assert service.repository.get(old_id).id == old_id
    search_ids = {row["id"] for row in service.search([1.0], "p", query_text="old fact")}
    assert old_id not in search_ids
    assert new_id in search_ids
    assert service.get_latest("p", "note")["id"] == new_id
    assert [row["id"] for row in service.get_recent("p", "note")] == [new_id]


def test_latest_and_recent_use_created_at_and_hide_superseded(service):
    first = service.add_memory([1.0], "first checkpoint", "p", "checkpoint")
    second = service.add_memory([1.0], "second checkpoint", "p", "checkpoint")
    service.set_status(first, "superseded")

    assert service.get_latest("p", "checkpoint")["id"] == second
    assert [row["id"] for row in service.get_recent("p", "checkpoint")] == [second]
    assert service.get_recent("p", "checkpoint", include_superseded=True)[0]["id"] == second


def test_status_history_can_be_included_in_search(service):
    old_id = service.add_memory([1.0], "old fact", "p", "note")
    service.set_status(old_id, "superseded")

    assert service.search([1.0], "p", query_text="old fact") == []
    assert service.search([1.0], "p", query_text="old fact", include_superseded=True)[0]["id"] == old_id


def test_link_records_relation_and_supersedes_target(service):
    source_id = service.add_memory([1.0], "source", "p", "note")
    target_id = service.add_memory([1.0], "target", "p", "note")

    service.link_memories(source_id, "supersedes", target_id)

    assert service.repository.get(source_id).relations == [{"type": "supersedes", "target": target_id}]
    target = service.repository.get(target_id)
    assert target.status == "superseded"
    assert target.invalid_at is not None


def test_set_status_sets_invalid_at_only_for_superseded_or_expired(service):
    resolved_id = service.add_memory([1.0], "resolved", "p", "note")
    expired_id = service.add_memory([1.0], "expired", "p", "note")
    superseded_id = service.add_memory([1.0], "superseded", "p", "note")

    service.set_status(resolved_id, "resolved")
    service.set_status(expired_id, "expired")
    service.set_status(superseded_id, "superseded")

    assert service.repository.get(resolved_id).invalid_at is None
    assert service.repository.get(expired_id).invalid_at is not None
    assert service.repository.get(superseded_id).invalid_at is not None


def test_link_requires_existing_source(service):
    with pytest.raises(ValueError, match="no memory found"):
        service.link_memories(str(uuid.uuid4()), "related_to", str(uuid.uuid4()))


def test_rrf_merges_vector_and_sqlite_substring_rankings(service):
    lexical_id = service.add_memory([0.0], "contains exact-token", "p", "note")
    vector_id = service.add_memory([1.0], "unrelated", "p", "note")

    results = service.search([1.0], "p", query_text="exact-token", k=2)

    assert {row["id"] for row in results} == {lexical_id, vector_id}
    assert all("content" in row and "score" in row for row in results)


def test_document_lookup_is_project_scoped_and_replaces_in_place(service):
    first_id = service.set_document([1.0], "version one", "p", "slug", "overview")
    second_id = service.set_document([1.0], "version two", "q", "slug", "overview")

    assert service.get_document("p", "slug")["id"] == first_id
    assert service.get_document("p", "slug")["content"] == "version one"
    assert service.get_document("q", "slug")["id"] == second_id
    assert service.get_document("missing", "slug") is None


def test_source_locator_is_preserved_as_provenance(service):
    memory_id = service.add_memory([1.0], "imported", "p", "note", source="notes.md")

    row = service.repository.get(memory_id)

    assert row.source_id
    assert service.get_latest("p", "note")["source"] == "notes.md"


def test_global_search_is_explicit_and_can_filter_type(service):
    p_id = service.add_memory([1.0], "p note", "p", "note")
    service.add_memory([1.0], "p bug", "p", "bug")
    q_id = service.add_memory([1.0], "q note", "q", "note")

    result_ids = {row["id"] for row in service.search_global([1.0], type_="note", k=5)}

    assert result_ids == {p_id, q_id}


def test_graph_records_join_authoritative_rows_to_vectors(service):
    memory_id = service.add_memory([1.0, 2.0], "graph record", "p", "note")

    records = service.get_all_with_vectors("p")

    assert records[0]["id"] == memory_id
    assert records[0]["content"] == "graph record"
    assert records[0]["vector"] == [1.0, 2.0]
