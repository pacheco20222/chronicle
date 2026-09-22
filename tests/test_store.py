import random
import time
import uuid

import pytest

from mnemo import store


def _vector(seed: int) -> list[float]:
    rng = random.Random(seed)
    return [rng.random() for _ in range(768)]


@pytest.fixture
def client():
    return store.get_client()


@pytest.fixture
def collection():
    return f"memories_test_{uuid.uuid4().hex[:8]}"


def test_ensure_collection_creates_once(client, collection):
    assert not client.collection_exists(collection)
    store.ensure_collection(client, collection)
    assert client.collection_exists(collection)
    store.ensure_collection(client, collection)  # idempotent, no error
    client.delete_collection(collection)


def test_add_and_search_scoped_by_project(client, collection):
    store.ensure_collection(client, collection)
    try:
        v = _vector(1)
        mem_id = store.add_memory(
            client, v, "use uv for python deps", "mcp-llm-brain", "decision",
            collection=collection,
        )
        assert mem_id

        results = store.search_memory(client, v, "mcp-llm-brain", collection=collection)
        assert len(results) == 1
        assert results[0]["id"] == mem_id
        assert results[0]["content"] == "use uv for python deps"
        assert results[0]["project"] == "mcp-llm-brain"
        assert results[0]["type"] == "decision"

        other_project = store.search_memory(client, v, "villenca", collection=collection)
        assert other_project == []
    finally:
        client.delete_collection(collection)


def test_search_filters_by_type(client, collection):
    store.ensure_collection(client, collection)
    try:
        store.add_memory(client, _vector(2), "bug memory", "mcp-llm-brain", "bug", collection=collection)
        store.add_memory(client, _vector(3), "note memory", "mcp-llm-brain", "note", collection=collection)

        bugs = store.search_memory(client, _vector(2), "mcp-llm-brain", type_="bug", k=5, collection=collection)
        assert len(bugs) == 1
        assert bugs[0]["type"] == "bug"
    finally:
        client.delete_collection(collection)


def test_search_respects_k(client, collection):
    store.ensure_collection(client, collection)
    try:
        for i in range(3):
            store.add_memory(client, _vector(10 + i), f"memory {i}", "mcp-llm-brain", "note", collection=collection)

        results = store.search_memory(client, _vector(10), "mcp-llm-brain", k=2, collection=collection)
        assert len(results) == 2
    finally:
        client.delete_collection(collection)


def test_get_latest_returns_none_when_nothing_matches(client, collection):
    store.ensure_collection(client, collection)
    try:
        assert store.get_latest(client, "mcp-llm-brain", "checkpoint", collection=collection) is None
    finally:
        client.delete_collection(collection)


def test_get_latest_returns_newest_by_created_at(client, collection):
    store.ensure_collection(client, collection)
    try:
        store.add_memory(client, _vector(20), "first checkpoint", "mcp-llm-brain", "checkpoint", collection=collection)
        time.sleep(0.01)
        newest_id = store.add_memory(client, _vector(21), "second checkpoint", "mcp-llm-brain", "checkpoint", collection=collection)

        latest = store.get_latest(client, "mcp-llm-brain", "checkpoint", collection=collection)
        assert latest is not None
        assert latest["id"] == newest_id
        assert latest["content"] == "second checkpoint"
    finally:
        client.delete_collection(collection)


def test_get_latest_filters_by_type(client, collection):
    store.ensure_collection(client, collection)
    try:
        store.add_memory(client, _vector(22), "a note", "mcp-llm-brain", "note", collection=collection)
        checkpoint_id = store.add_memory(client, _vector(23), "a checkpoint", "mcp-llm-brain", "checkpoint", collection=collection)

        latest = store.get_latest(client, "mcp-llm-brain", "checkpoint", collection=collection)
        assert latest is not None
        assert latest["id"] == checkpoint_id
    finally:
        client.delete_collection(collection)


def test_add_memory_defaults_to_active_status(client, collection):
    store.ensure_collection(client, collection)
    try:
        mem_id = store.add_memory(client, _vector(40), "a note", "mcp-llm-brain", "note", collection=collection)
        results = store.search_memory(client, _vector(40), "mcp-llm-brain", k=5, collection=collection)
        assert results[0]["id"] == mem_id
        assert results[0]["status"] == "active"
        assert results[0]["supersedes"] is None
    finally:
        client.delete_collection(collection)


def test_search_memory_excludes_superseded_by_default(client, collection):
    store.ensure_collection(client, collection)
    try:
        old_id = store.add_memory(client, _vector(41), "old fact", "mcp-llm-brain", "note", collection=collection)
        store.set_status(client, old_id, "superseded", collection=collection)

        results = store.search_memory(client, _vector(41), "mcp-llm-brain", k=5, collection=collection)
        assert results == []

        results_with_history = store.search_memory(
            client, _vector(41), "mcp-llm-brain", k=5, include_superseded=True, collection=collection
        )
        assert len(results_with_history) == 1
        assert results_with_history[0]["id"] == old_id
    finally:
        client.delete_collection(collection)


def test_add_memory_with_supersedes_marks_old_memory_superseded(client, collection):
    store.ensure_collection(client, collection)
    try:
        old_id = store.add_memory(client, _vector(42), "old fact", "mcp-llm-brain", "note", collection=collection)
        new_id = store.add_memory(
            client, _vector(42), "corrected fact", "mcp-llm-brain", "note",
            supersedes=old_id, collection=collection,
        )

        results = store.search_memory(client, _vector(42), "mcp-llm-brain", k=5, collection=collection)
        ids = {r["id"] for r in results}
        assert new_id in ids
        assert old_id not in ids

        new_record = next(r for r in results if r["id"] == new_id)
        assert new_record["supersedes"] == old_id
    finally:
        client.delete_collection(collection)


def test_get_latest_and_get_recent_exclude_superseded_by_default(client, collection):
    store.ensure_collection(client, collection)
    try:
        old_id = store.add_memory(client, _vector(43), "old checkpoint", "mcp-llm-brain", "checkpoint", collection=collection)
        time.sleep(0.01)
        new_id = store.add_memory(client, _vector(44), "new checkpoint", "mcp-llm-brain", "checkpoint", collection=collection)
        store.set_status(client, old_id, "superseded", collection=collection)

        latest = store.get_latest(client, "mcp-llm-brain", "checkpoint", collection=collection)
        assert latest["id"] == new_id

        recent = store.get_recent(client, "mcp-llm-brain", "checkpoint", collection=collection)
        assert [r["id"] for r in recent] == [new_id]

        recent_with_history = store.get_recent(
            client, "mcp-llm-brain", "checkpoint", include_superseded=True, collection=collection
        )
        assert {r["id"] for r in recent_with_history} == {old_id, new_id}
    finally:
        client.delete_collection(collection)


def test_link_memories_appends_typed_relation(client, collection):
    store.ensure_collection(client, collection)
    try:
        a_id = store.add_memory(client, _vector(50), "memory a", "mcp-llm-brain", "note", collection=collection)
        b_id = store.add_memory(client, _vector(51), "memory b", "mcp-llm-brain", "note", collection=collection)

        store.link_memories(client, a_id, "related_to", b_id, collection=collection)

        results = store.search_memory(client, _vector(50), "mcp-llm-brain", k=5, collection=collection)
        a_record = next(r for r in results if r["id"] == a_id)
        assert a_record["relations"] == [{"type": "related_to", "target": b_id}]
    finally:
        client.delete_collection(collection)


def test_link_memories_supersedes_marks_target_superseded(client, collection):
    store.ensure_collection(client, collection)
    try:
        old_id = store.add_memory(client, _vector(52), "old memory", "mcp-llm-brain", "note", collection=collection)
        new_id = store.add_memory(client, _vector(53), "new memory", "mcp-llm-brain", "note", collection=collection)

        store.link_memories(client, new_id, "supersedes", old_id, collection=collection)

        results = store.search_memory(client, _vector(53), "mcp-llm-brain", k=5, collection=collection)
        result_ids = {r["id"] for r in results}
        assert new_id in result_ids
        assert old_id not in result_ids
    finally:
        client.delete_collection(collection)


def test_link_memories_raises_for_unknown_source(client, collection):
    store.ensure_collection(client, collection)
    try:
        missing_id = str(uuid.uuid4())
        with pytest.raises(ValueError):
            store.link_memories(client, missing_id, "related_to", str(uuid.uuid4()), collection=collection)
    finally:
        client.delete_collection(collection)


class _FakePoint:
    def __init__(self, id_, payload):
        self.id = id_
        self.payload = payload


def test_rrf_merge_boosts_ids_present_in_multiple_lists():
    vector_ranked = [_FakePoint("a", {"content": "a"}), _FakePoint("b", {"content": "b"})]
    lexical_ranked = [_FakePoint("b", {"content": "b"}), _FakePoint("c", {"content": "c"})]

    merged = store._rrf_merge([vector_ranked, lexical_ranked], k=5)
    ids = [m["id"] for m in merged]

    assert ids[0] == "b"  # present in both lists, ranks first
    assert set(ids) == {"a", "b", "c"}


def test_rrf_merge_truncates_to_k():
    ranked = [_FakePoint(str(i), {"content": str(i)}) for i in range(10)]
    merged = store._rrf_merge([ranked], k=3)
    assert len(merged) == 3


def test_search_memory_lexical_match_surfaces_despite_poor_vector_rank(client, collection):
    store.ensure_collection(client, collection)
    try:
        distractor_id = store.add_memory(client, _vector(70), "distractor content", "mcp-llm-brain", "note", collection=collection)
        target_id = store.add_memory(
            client, _vector(9999), "grep for ERR_CODE_88421 in the log parser", "mcp-llm-brain", "bug",
            collection=collection,
        )
        query_vector = _vector(70)  # identical to the distractor's vector -> distractor wins on pure similarity

        vector_only = store.search_memory(client, query_vector, "mcp-llm-brain", k=1, collection=collection)
        assert vector_only[0]["id"] == distractor_id

        hybrid = store.search_memory(
            client, query_vector, "mcp-llm-brain", query_text="ERR_CODE_88421", k=1, collection=collection
        )
        assert hybrid[0]["id"] == target_id
    finally:
        client.delete_collection(collection)


def test_get_document_returns_none_for_unknown_slug(client, collection):
    store.ensure_collection(client, collection)
    try:
        assert store.get_document(client, "mcp-llm-brain", "no-such-doc", collection=collection) is None
    finally:
        client.delete_collection(collection)


def test_set_document_creates_then_replaces_in_place(client, collection):
    store.ensure_collection(client, collection)
    try:
        first_id = store.set_document(
            client, _vector(30), "version one", "mcp-llm-brain", "plan-test-doc", "note",
            collection=collection,
        )
        first = store.get_document(client, "mcp-llm-brain", "plan-test-doc", collection=collection)
        assert first["content"] == "version one"
        assert first["id"] == first_id

        time.sleep(0.01)
        second_id = store.set_document(
            client, _vector(31), "version two", "mcp-llm-brain", "plan-test-doc", "note",
            collection=collection,
        )
        assert second_id == first_id

        second = store.get_document(client, "mcp-llm-brain", "plan-test-doc", collection=collection)
        assert second["content"] == "version two"
        assert second["id"] == first_id
        assert second["created_at"] == first["created_at"]
        assert second["updated_at"] > first["updated_at"]
    finally:
        client.delete_collection(collection)


def test_search_memory_global_returns_results_across_projects(client, collection):
    store.ensure_collection(client, collection)
    try:
        v = _vector(40)
        villenca_id = store.add_memory(client, v, "villenca note", "villenca", "note", collection=collection)
        brain_id = store.add_memory(client, v, "mcp-llm-brain note", "mcp-llm-brain", "note", collection=collection)

        results = store.search_memory_global(client, v, k=10, collection=collection)
        result_ids = {r["id"] for r in results}
        assert villenca_id in result_ids
        assert brain_id in result_ids
    finally:
        client.delete_collection(collection)


def test_search_memory_global_excludes_superseded_by_default(client, collection):
    store.ensure_collection(client, collection)
    try:
        v = _vector(45)
        old_id = store.add_memory(client, v, "old villenca note", "villenca", "note", collection=collection)
        store.set_status(client, old_id, "superseded", collection=collection)

        results = store.search_memory_global(client, v, k=10, collection=collection)
        assert old_id not in {r["id"] for r in results}

        results_with_history = store.search_memory_global(client, v, k=10, include_superseded=True, collection=collection)
        assert old_id in {r["id"] for r in results_with_history}
    finally:
        client.delete_collection(collection)


def test_search_memory_global_lexical_match_surfaces_despite_poor_vector_rank(client, collection):
    store.ensure_collection(client, collection)
    try:
        distractor_id = store.add_memory(client, _vector(71), "distractor content", "villenca", "note", collection=collection)
        target_id = store.add_memory(
            client, _vector(9998), "see ERR_CODE_77331 in the parser", "villenca", "bug", collection=collection
        )
        query_vector = _vector(71)

        hybrid = store.search_memory_global(
            client, query_vector, query_text="ERR_CODE_77331", k=1, collection=collection
        )
        assert hybrid[0]["id"] == target_id
        assert distractor_id  # sanity: distractor was created
    finally:
        client.delete_collection(collection)


def test_search_memory_global_filters_by_type(client, collection):
    store.ensure_collection(client, collection)
    try:
        v = _vector(41)
        note_id = store.add_memory(client, v, "a note", "villenca", "note", collection=collection)
        store.add_memory(client, v, "a bug", "villenca", "bug", collection=collection)

        results = store.search_memory_global(client, v, type_="note", k=10, collection=collection)
        result_ids = {r["id"] for r in results}
        assert note_id in result_ids
        assert all(r["type"] == "note" for r in results)
    finally:
        client.delete_collection(collection)


def test_search_memory_global_respects_k(client, collection):
    store.ensure_collection(client, collection)
    try:
        v = _vector(42)
        for i in range(5):
            store.add_memory(client, v, f"note {i}", "villenca", "note", collection=collection)

        results = store.search_memory_global(client, v, k=3, collection=collection)
        assert len(results) == 3
    finally:
        client.delete_collection(collection)


def test_get_all_with_vectors_returns_vectors(client, collection):
    store.ensure_collection(client, collection)
    try:
        store.add_memory(client, _vector(50), "first", "mcp-llm-brain", "note", collection=collection)
        store.add_memory(client, _vector(51), "second", "mcp-llm-brain", "note", collection=collection)

        records = store.get_all_with_vectors(client, collection=collection)
        assert len(records) == 2
        assert all("vector" in r and len(r["vector"]) == 768 for r in records)
        assert all("content" in r for r in records)
    finally:
        client.delete_collection(collection)


def test_get_all_with_vectors_filters_by_project(client, collection):
    store.ensure_collection(client, collection)
    try:
        store.add_memory(client, _vector(52), "villenca note", "villenca", "note", collection=collection)
        store.add_memory(client, _vector(53), "brain note", "mcp-llm-brain", "note", collection=collection)

        records = store.get_all_with_vectors(client, project="villenca", collection=collection)
        assert len(records) == 1
        assert records[0]["project"] == "villenca"
    finally:
        client.delete_collection(collection)


def test_set_document_same_slug_different_project_are_independent(client, collection):
    store.ensure_collection(client, collection)
    try:
        store.set_document(client, _vector(32), "villenca's doc", "villenca", "overview", "architecture", collection=collection)
        store.set_document(client, _vector(33), "mcp-llm-brain's doc", "mcp-llm-brain", "overview", "architecture", collection=collection)

        villenca_doc = store.get_document(client, "villenca", "overview", collection=collection)
        brain_doc = store.get_document(client, "mcp-llm-brain", "overview", collection=collection)
        assert villenca_doc["content"] == "villenca's doc"
        assert brain_doc["content"] == "mcp-llm-brain's doc"
        assert villenca_doc["id"] != brain_doc["id"]
    finally:
        client.delete_collection(collection)
