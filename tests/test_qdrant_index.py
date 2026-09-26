import uuid

import pytest

from chronicle.core.qdrant_index import QdrantVectorIndex


def test_qdrant_adapter_round_trip_against_local_service():
    collection = f"chronicle_test_{uuid.uuid4().hex}"
    try:
        index = QdrantVectorIndex(collection=collection)
    except Exception as exc:
        pytest.skip(f"local Qdrant unavailable: {type(exc).__name__}")

    memory_id = str(uuid.uuid4())
    try:
        index.upsert(memory_id, [1.0] * 768, {"project": "p", "type": "note"})
        hits = index.search([1.0] * 768, "p", 1, {"type": "note"})
        assert hits[0].id == memory_id
    finally:
        index.delete(memory_id)
        index.client.delete_collection(collection)
