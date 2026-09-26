from pathlib import Path

import anyio
import pytest
from fastmcp import Client

from mnemo import config, registry, server


def test_memory_add_and_search_round_trip():
    added = server.memory_add("prefer uv over pip for this project", "decision")
    assert added["project"] == config.get_project()
    assert added["type"] == "decision"
    assert added["id"]

    results = server.memory_search("what package manager should I use")
    assert any(r["id"] == added["id"] for r in results)


def test_memory_add_provenance_round_trip():
    added = server.memory_add(
        "manual provenance via MCP tool",
        "note",
        confidence=0.8,
        extraction_method="manual",
    )

    latest = server.memory_get_latest("note")
    results = server.memory_search("manual provenance via MCP tool")

    assert latest["id"] == added["id"]
    assert latest["confidence"] == 0.8
    assert latest["extraction_method"] == "manual"
    result = next(row for row in results if row["id"] == added["id"])
    assert result["confidence"] == 0.8
    assert result["extraction_method"] == "manual"


def test_memory_add_rejects_invalid_type():
    with pytest.raises(ValueError):
        server.memory_add("bad type memory", "nonsense")


def test_memory_search_finds_exact_technical_token():
    added = server.memory_add("grep for ERR_CODE_55219 before touching the log parser", "bug")
    results = server.memory_search("ERR_CODE_55219")
    assert any(r["id"] == added["id"] for r in results)


def test_memory_search_filters_by_type():
    added = server.memory_add("a specific bug about vector size mismatch", "bug")
    bugs = server.memory_search("vector size mismatch", type="bug")
    assert any(r["id"] == added["id"] for r in bugs)


def test_mcp_protocol_round_trip():
    async def run():
        async with Client(server.mcp) as client:
            add_result = await client.call_tool(
                "memory_add", {"content": "mcp protocol smoke test", "type": "note"}
            )
            assert add_result.data["project"] == config.get_project()

            search_result = await client.call_tool(
                "memory_search", {"query": "mcp protocol smoke test"}
            )
            assert any(r["id"] == add_result.data["id"] for r in search_result.data)

    anyio.run(run)


def test_server_instructions_cover_checkpoint_workflow():
    assert "checkpoint" in server.mcp.instructions
    assert "memory_add" in server.mcp.instructions


def test_memory_add_with_supersedes_hides_old_memory_from_search():
    old = server.memory_add("old fact about the deploy process", "note")
    new = server.memory_add("corrected fact about the deploy process", "note", supersedes=old["id"])
    assert new["supersedes"] == old["id"]

    results = server.memory_search("fact about the deploy process")
    result_ids = {r["id"] for r in results}
    assert new["id"] in result_ids
    assert old["id"] not in result_ids


def test_memory_set_status_marks_memory_resolved():
    added = server.memory_add("a bug that will get fixed", "bug")
    result = server.memory_set_status(added["id"], "resolved")
    assert result == {"id": added["id"], "status": "resolved"}


def test_memory_set_status_rejects_invalid_status():
    added = server.memory_add("a memory", "note")
    with pytest.raises(ValueError):
        server.memory_set_status(added["id"], "nonsense")


def test_memory_link_records_typed_relation():
    a = server.memory_add("memory a", "note")
    b = server.memory_add("memory b", "note")

    result = server.memory_link(a["id"], "blocked_by", b["id"])
    assert result == {"source_id": a["id"], "relation_type": "blocked_by", "target_id": b["id"]}


def test_memory_link_rejects_invalid_relation_type():
    a = server.memory_add("memory a", "note")
    b = server.memory_add("memory b", "note")
    with pytest.raises(ValueError):
        server.memory_link(a["id"], "nonsense", b["id"])


def test_memory_set_document_creates_and_replaces():
    first = server.memory_set_document("plan-test-doc", "version one", "note")
    assert first["slug"] == "plan-test-doc"
    assert first["content"] == "version one"

    fetched = server.memory_get_document("plan-test-doc")
    assert fetched is not None
    assert fetched["content"] == "version one"
    assert fetched["id"] == first["id"]

    second = server.memory_set_document("plan-test-doc", "version two", "note")
    assert second["id"] == first["id"]

    fetched_again = server.memory_get_document("plan-test-doc")
    assert fetched_again["content"] == "version two"
    assert fetched_again["id"] == first["id"]


def test_memory_set_document_provenance_round_trip():
    server.memory_set_document(
        "provenance-protocol-doc",
        "document provenance",
        "note",
        confidence=0.8,
        extraction_method="manual",
    )

    document = server.memory_get_document("provenance-protocol-doc")

    assert document["confidence"] == 0.8
    assert document["extraction_method"] == "manual"


def test_memory_get_document_returns_none_for_unknown_slug():
    assert server.memory_get_document("a-slug-that-was-never-set") is None


def test_memory_get_latest_returns_newest_by_timestamp_not_relevance():
    server.memory_add("older checkpoint, textually very similar to the query", "checkpoint")
    newest = server.memory_add("totally unrelated wording checkpoint", "checkpoint")

    latest = server.memory_get_latest("checkpoint")
    assert latest["id"] == newest["id"]


def test_memory_get_latest_returns_none_when_nothing_saved():
    assert server.memory_get_latest("todo") is None


def test_memory_get_latest_rejects_invalid_type():
    with pytest.raises(ValueError):
        server.memory_get_latest("nonsense")


def test_mcp_protocol_document_round_trip():
    async def run():
        async with Client(server.mcp) as client:
            set_result = await client.call_tool(
                "memory_set_document", {"slug": "protocol-test-doc", "content": "hello", "type": "note"}
            )
            assert set_result.data["slug"] == "protocol-test-doc"

            get_result = await client.call_tool("memory_get_document", {"slug": "protocol-test-doc"})
            assert get_result.data["content"] == "hello"

            missing_result = await client.call_tool(
                "memory_get_document", {"slug": "definitely-not-a-real-slug"}
            )
            assert missing_result.data is None

    anyio.run(run)


def test_server_instructions_cover_document_workflow():
    assert "memory_set_document" in server.mcp.instructions
    assert "memory_get_document" in server.mcp.instructions


def test_memory_search_global_sees_other_projects(service):
    other_id = service.add_memory(
        [0.1] * 768,
        "cross-project global search probe",
        "a-totally-different-project",
        "note",
    )

    results = server.memory_search_global("cross-project global search probe")
    assert any(r["id"] == other_id for r in results)


def test_mcp_protocol_global_search_round_trip():
    async def run():
        async with Client(server.mcp) as client:
            add_result = await client.call_tool(
                "memory_add", {"content": "protocol global search probe", "type": "note"}
            )
            search_result = await client.call_tool(
                "memory_search_global", {"query": "protocol global search probe"}
            )
            assert any(r["id"] == add_result.data["id"] for r in search_result.data)

    anyio.run(run)


def test_server_instructions_cover_global_search_scope():
    assert "memory_search_global" in server.mcp.instructions
    assert "every project" in server.mcp.instructions


def test_memory_register_project_writes_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("MNEMO_REGISTRY_PATH", str(tmp_path / "projects.json"))
    result = server.memory_register_project("registered-via-tool")
    assert result["project"] == "registered-via-tool"
    assert registry.lookup(Path.cwd()) == "registered-via-tool"


def test_server_instructions_cover_registration_workflow():
    assert "memory_register_project" in server.mcp.instructions


def test_memory_register_project_rejects_empty_name(tmp_path, monkeypatch):
    monkeypatch.setenv("MNEMO_REGISTRY_PATH", str(tmp_path / "projects.json"))
    with pytest.raises(ValueError):
        server.memory_register_project("   ")


def test_memory_search_checkpoint_type_is_newest_first_ignoring_query():
    server.memory_add("alpha deployment kubernetes rollout notes", "checkpoint")
    newest = server.memory_add("zzz unrelated newest checkpoint", "checkpoint")
    results = server.memory_search("alpha deployment kubernetes rollout", type="checkpoint", k=5)
    assert results[0]["id"] == newest["id"]
    stamps = [r["created_at"] for r in results]
    assert stamps == sorted(stamps, reverse=True)
