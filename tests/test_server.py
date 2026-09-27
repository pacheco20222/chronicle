import inspect
from pathlib import Path

import anyio
import pytest
from fastmcp import Client

from chronicle import config, registry, server


def test_memory_add_and_search_round_trip():
    added = server.memory_add("prefer uv over pip for this project", "decision")
    assert added["project"] == config.get_project()
    assert added["type"] == "decision"
    assert added["id"]

    results = server.memory_search("what package manager should I use")
    assert any(r["id"] == added["id"] for r in results)


def test_memory_add_at_scope_path_targets_explicit_project():
    added = server.memory_add(
        "chat-specific memory", "note", scope_path="personal/chat"
    )

    assert added["project"] == "personal/chat"


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


def test_memory_search_at_scope_path_targets_explicit_project(service):
    target_id = service.add_memory(
        [0.1] * 768, "chat-specific search memory", "personal/search", "note"
    )

    results = server.memory_search("chat-specific search memory", scope_path="personal/search")

    assert any(result["id"] == target_id for result in results)


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


def test_memory_list_scopes_tool(service):
    service.repository.get_or_create_scope("work/azure")
    result = server.memory_list_scopes(prefix="work")
    assert {item["path"] for item in result} == {"work", "work/azure"}


def test_memory_list_scopes_no_match_returns_empty():
    assert server.memory_list_scopes(prefix="nonexistent") == []


def test_memory_set_document_at_scope_path_creates_ancestors(service):
    result = server.memory_set_document(
        slug="work", content="work domain core", type="overview", scope_path="work/azure"
    )
    assert result["project"] == "work/azure"
    assert service.repository.get_scope_by_path("work") is not None
    assert service.repository.get_scope_by_path("work/azure") is not None


def test_memory_get_document_at_scope_path(service):
    server.memory_set_document(
        slug="work/azure", content="azure notes", type="overview", scope_path="work/azure"
    )
    result = server.memory_get_document(slug="work/azure", scope_path="work/azure")
    assert result["content"] == "azure notes"


def test_memory_get_document_at_scope_path_falls_back_to_bare_name_after_reparent(service):
    server.memory_set_document(slug="chronicle-test", content="the real overview", type="overview")
    service.repository.get_or_create_scope("personal_projects")
    service.reparent_scope("chronicle-test", "personal_projects")

    result = server.memory_get_document(slug="personal_projects/chronicle-test", scope_path="personal_projects/chronicle-test")
    assert result is not None
    assert result["content"] == "the real overview"


def test_memory_get_document_at_missing_scope_path_returns_none():
    assert server.memory_get_document(slug="x", scope_path="never/created") is None


def test_memory_set_document_without_scope_path_unchanged():
    result = server.memory_set_document(slug="chronicle-test", content="c", type="overview")
    assert result["project"] == "chronicle-test"


def test_memory_get_by_source_tool(service):
    v = [0.1] * 768
    id0 = service.add_memory(v, "chunk 0", "chronicle-test", "document", source="doc.md", chunk_index=0)
    source_id = service.repository.get(id0).source_id
    result = server.memory_get_by_source(source_id=source_id)
    assert result[0]["id"] == id0


def test_memory_link_accepts_relates_to_project(service):
    v = [0.1] * 768
    target_id = service.set_document(v, "overview", "chronicle-test", "chronicle-test", "overview")
    doc_id = service.add_memory(v, "doc", "docs/general", "document")
    result = server.memory_link(
        source_id=doc_id, relation_type="relates_to_project", target_id=target_id
    )
    assert result["relation_type"] == "relates_to_project"


def test_memory_search_include_linked_param(service):
    v = [0.1] * 768
    target_id = service.set_document(v, "overview", "chronicle-test", "chronicle-test", "overview")
    doc_id = service.add_memory(v, "widget spec details", "docs/general", "document")
    service.link_memories(doc_id, "relates_to_project", target_id)
    results = server.memory_search(query="widget", include_linked=True)
    assert any(r["id"] == doc_id for r in results)


def test_memory_dashboard_graph_includes_scopes(service):
    v = [0.1] * 768
    service.set_document(v, "azure core", "work/azure", "work/azure", "overview")
    service.add_memory(v, "unrelated memory", "chronicle-test", "note")
    service.repository.get_or_create_scope("work/azure/vm_config")

    result = server.memory_dashboard_graph(project="chronicle-test")
    assert "scopes" in result
    paths = {s["path"] for s in result["scopes"]}
    assert {"work", "work/azure", "work/azure/vm_config", "chronicle-test"} <= paths
    azure = next(s for s in result["scopes"] if s["path"] == "work/azure")
    assert azure["core_present"] is True
    assert azure["child_count"] == 1


def test_memory_scope_reparent_tool(service):
    service.repository.get_or_create_scope("chronicle")
    service.repository.get_or_create_scope("work")
    result = server.memory_scope_reparent(path="chronicle", new_parent_path="work")
    assert result["path"] == "work/chronicle"


def test_memory_get_latest_returns_newest_by_timestamp_not_relevance():
    server.memory_add("older checkpoint, textually very similar to the query", "checkpoint")
    newest = server.memory_add("totally unrelated wording checkpoint", "checkpoint")

    latest = server.memory_get_latest("checkpoint")
    assert latest["id"] == newest["id"]


def test_memory_get_latest_at_scope_path_targets_explicit_project(service):
    target_id = service.add_memory(
        [0.1] * 768, "chat-specific latest checkpoint", "personal/latest", "checkpoint"
    )

    latest = server.memory_get_latest("checkpoint", scope_path="personal/latest")

    assert latest["id"] == target_id


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
    assert "max_tokens" in server.mcp.instructions


def test_search_tools_accept_optional_token_budget():
    assert "max_tokens" in inspect.signature(server.memory_search).parameters
    assert "max_tokens" in inspect.signature(server.memory_search_global).parameters


def test_memory_register_project_writes_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("CHRONICLE_REGISTRY_PATH", str(tmp_path / "projects.json"))
    result = server.memory_register_project("registered-via-tool")
    assert result["project"] == "registered-via-tool"
    assert registry.lookup(Path.cwd()) == "registered-via-tool"


def test_server_instructions_cover_registration_workflow():
    assert "memory_register_project" in server.mcp.instructions


def test_memory_correction_tools_round_trip():
    added = server.memory_add("correction workflow source", "note", confidence=0.2)

    confirmed = server.memory_confirm(added["id"], confidence=0.9)
    assert confirmed == {"id": added["id"], "confidence": 0.9}

    edited = server.memory_edit(added["id"], "correction workflow edited")
    assert edited == {"id": added["id"], "content": "correction workflow edited"}
    assert any(row["id"] == added["id"] for row in server.memory_search("correction workflow edited"))

    retracted = server.memory_retract(added["id"])
    assert retracted == {"id": added["id"], "status": "deleted"}

    wrong = server.memory_add("incorrect extracted fact", "note")
    marked_wrong = server.memory_mark_wrong(wrong["id"])
    assert marked_wrong == {"id": wrong["id"], "status": "wrong"}

    source_a = server.memory_add("merge source a", "note")
    source_b = server.memory_add("merge source b", "note")
    merged = server.memory_merge("merged correction", "note", [source_a["id"], source_b["id"]])
    assert merged["id"]

    split_source = server.memory_add("combined correction", "note")
    split = server.memory_split(
        split_source["id"],
        [{"content": "split correction one", "type": "note"}, {"content": "split correction two", "type": "note"}],
    )
    assert len(split["ids"]) == 2


def test_memory_merge_at_scope_path_targets_explicit_project(service):
    source_a = service.add_memory([0.1] * 768, "merge source a", "personal/merge", "note")
    source_b = service.add_memory([0.1] * 768, "merge source b", "personal/merge", "note")

    merged = server.memory_merge(
        "merged explicit scope", "note", [source_a, source_b], scope_path="personal/merge"
    )

    assert merged["project"] == "personal/merge"
    assert service.repository.get(merged["id"]).project == "personal/merge"


def test_server_instructions_cover_correction_workflow():
    for tool in (
        "memory_confirm",
        "memory_edit",
        "memory_retract",
        "memory_mark_wrong",
        "memory_merge",
        "memory_split",
    ):
        assert tool in server.mcp.instructions


def test_memory_register_project_rejects_empty_name(tmp_path, monkeypatch):
    monkeypatch.setenv("CHRONICLE_REGISTRY_PATH", str(tmp_path / "projects.json"))
    with pytest.raises(ValueError):
        server.memory_register_project("   ")


def test_memory_search_checkpoint_type_is_newest_first_ignoring_query():
    server.memory_add("alpha deployment kubernetes rollout notes", "checkpoint")
    newest = server.memory_add("zzz unrelated newest checkpoint", "checkpoint")
    results = server.memory_search("alpha deployment kubernetes rollout", type="checkpoint", k=5)
    assert results[0]["id"] == newest["id"]
    stamps = [r["created_at"] for r in results]
    assert stamps == sorted(stamps, reverse=True)
