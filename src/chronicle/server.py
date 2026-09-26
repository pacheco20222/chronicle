from pathlib import Path

from fastmcp import FastMCP

from chronicle import config, dashboard, embeddings, graph_cli, registry
from chronicle.core.runtime import get_runtime

mcp = FastMCP(
    "chronicle",
    instructions=(
        "This server stores project-scoped memories. When the user asks to "
        "checkpoint progress (e.g. says \"checkpoint this\" or asks to save "
        "where things stand before clearing the session), call memory_add "
        "with type=\"checkpoint\" and content summarizing: the current "
        "state, what's been tried (including things that did NOT work), "
        "and the concrete next step. Write it so that someone with zero "
        "memory of this conversation could resume the work from it alone. "
        "Optional memory_add provenance fields are confidence and extraction_method. "
        "For content that should persist and update in place over time "
        "(a project overview, an evolving bug list, anything that "
        "supersedes its previous version rather than adding to it), use "
        "memory_set_document(slug, content, type) instead of memory_add — "
        "it replaces any existing document with the same slug rather than "
        "creating a duplicate. Use memory_get_document(slug) to read one "
        "back by name. The project overview document's slug should be the "
        "project's own name. When asked for the latest/most recent memory "
        "of a given type (e.g. \"what's the latest checkpoint\"), call "
        "memory_get_latest(type) — it returns the newest one by actual "
        "timestamp. Never use memory_search for this: it ranks by semantic "
        "similarity to the query text, not recency, and can surface an "
        "older but more textually-relevant memory instead of the newest "
        "one. memory_search with type=\"checkpoint\" also returns checkpoints "
        "newest-first (query ignored), so it can never surface a stale one "
        "ahead of the latest. The project overview document is NOT a checkpoint — never "
        "present it as one. There is also memory_search_global(query, "
        "type, k, max_tokens), which searches across every project, not just this "
        "one. Only call it when the user explicitly asks for something "
        "cross-project (e.g. \"what have I done across all my "
        "projects\") — optional max_tokens bounds returned memory content; never as a "
        "fallback or default when the normal "
        "memory_search, scoped to this project, would do. If any memory "
        "tool call fails because no project is set for this folder, or "
        "the user explicitly asks to set up Chronicle here, call "
        "memory_register_project(name) with a short project id — it "
        "registers the current folder so every future call in it "
        "resolves automatically, immediately, no restart needed. Beyond "
        "explicit requests: if you notice a change worth reflecting in "
        "the project overview document, ask before updating it — don't "
        "update it silently. Separately, if a while has passed without "
        "saving anything and something notable has come up, ask whether "
        "to save it as a note — never save either one automatically. "
        "Every memory has a status: active, resolved, or superseded. "
        "Retrieval (memory_search, memory_search_global, memory_get_latest) "
        "hides superseded memories by default — treat them as gone unless "
        "someone explicitly asks for history. When a new memory replaces "
        "an old one outright, pass supersedes=<old memory id> to "
        "memory_add — this marks the old one superseded automatically. "
        "Use memory_set_status(memory_id, status) to mark something "
        "resolved (e.g. a bug that got fixed) without replacing it with a "
        "new memory. To record an explicit relationship between two "
        "existing memories (not just semantic similarity), call "
        "memory_link(source_id, relation_type, target_id) with "
        "relation_type one of: related_to, supersedes, caused_by, "
        "blocked_by, implements. Only call it when the relationship is "
        "worth remembering on its own, not for every passing mention. "
        "For human correction, use memory_confirm to adjust confidence, "
        "memory_edit to correct representation or extraction errors in "
        "place without creating history — use it only when the underlying "
        "meaning is unchanged (a typo, a misheard word, a formatting "
        "slip). If the correction changes what the memory actually "
        "claims, use memory_add with supersedes=<old memory id> instead, "
        "which preserves the old version as history. memory_retract "
        "to mark unwanted memory deleted, memory_mark_wrong for facts that "
        "were never true, memory_merge to combine sources, and memory_split "
        "to replace one source with fragments; use memory_add with "
        "supersedes for a genuinely new replacement fact and memory_link "
        "for relationships without replacement."
    ),
)

_service = None


def _get_service():
    global _service
    if _service is None:
        _service = get_runtime()
    return _service


@mcp.tool
def memory_add(
    content: str,
    type: str,
    supersedes: str | None = None,
    confidence: float | None = None,
    extraction_method: str | None = None,
) -> dict:
    project = config.get_project()
    config.validate_type(type)
    vector = embeddings.embed_text(content)
    memory_id = _get_service().add_memory(
        vector,
        content,
        project,
        type,
        supersedes=supersedes,
        confidence=confidence,
        extraction_method=extraction_method,
    )
    return {
        "id": memory_id,
        "project": project,
        "type": type,
        "content": content,
        "supersedes": supersedes,
        "confidence": confidence,
        "extraction_method": extraction_method,
    }


@mcp.tool
def memory_set_status(memory_id: str, status: str) -> dict:
    config.validate_status(status)
    _get_service().set_status(memory_id, status)
    return {"id": memory_id, "status": status}


@mcp.tool
def memory_confirm(memory_id: str, confidence: float = 1.0) -> dict:
    _get_service().confirm_memory(memory_id, confidence=confidence)
    return {"id": memory_id, "confidence": confidence}


@mcp.tool
def memory_edit(memory_id: str, content: str) -> dict:
    vector = embeddings.embed_text(content)
    _get_service().edit_memory(memory_id, content, vector)
    return {"id": memory_id, "content": content}


@mcp.tool
def memory_retract(memory_id: str) -> dict:
    _get_service().retract_memory(memory_id)
    return {"id": memory_id, "status": "deleted"}


@mcp.tool
def memory_mark_wrong(memory_id: str) -> dict:
    _get_service().mark_wrong(memory_id)
    return {"id": memory_id, "status": "wrong"}


@mcp.tool
def memory_link(source_id: str, relation_type: str, target_id: str) -> dict:
    config.validate_relation_type(relation_type)
    _get_service().link_memories(source_id, relation_type, target_id)
    return {"source_id": source_id, "relation_type": relation_type, "target_id": target_id}


@mcp.tool
def memory_merge(content: str, type: str, source_ids: list[str]) -> dict:
    project = config.get_project()
    config.validate_type(type)
    vector = embeddings.embed_text(content)
    memory_id = _get_service().merge_memories(vector, content, project, type, source_ids)
    return {
        "id": memory_id,
        "project": project,
        "type": type,
        "content": content,
        "source_ids": source_ids,
    }


@mcp.tool
def memory_split(source_id: str, new_memories: list[dict]) -> dict:
    contents = []
    for memory in new_memories:
        content = memory["content"]
        type_ = memory["type"]
        config.validate_type(type_)
        contents.append((embeddings.embed_text(content), content, type_))
    memory_ids = _get_service().split_memory(source_id, contents)
    return {"source_id": source_id, "ids": memory_ids}


@mcp.tool
def memory_search(
    query: str,
    type: str | None = None,
    k: int = 5,
    max_tokens: int | None = None,
) -> list[dict]:
    project = config.get_project()
    if type == "checkpoint":
        # Checkpoints are a timeline, not a topic: newest first, query ignored.
        return _get_service().get_recent(project, "checkpoint", k=k)
    vector = embeddings.embed_text(query)
    return _get_service().search(
        vector,
        project,
        query_text=query,
        type_=type,
        k=k,
        max_tokens=max_tokens,
    )


@mcp.tool
def memory_search_global(
    query: str,
    type: str | None = None,
    k: int = 5,
    max_tokens: int | None = None,
) -> list[dict]:
    vector = embeddings.embed_text(query)
    return _get_service().search_global(
        vector,
        query_text=query,
        type_=type,
        k=k,
        max_tokens=max_tokens,
    )


@mcp.tool
def memory_set_document(
    slug: str,
    content: str,
    type: str,
    confidence: float | None = None,
    extraction_method: str | None = None,
) -> dict:
    project = config.get_project()
    config.validate_type(type)
    vector = embeddings.embed_text(content)
    doc_id = _get_service().set_document(
        vector,
        content,
        project,
        slug,
        type,
        confidence=confidence,
        extraction_method=extraction_method,
    )
    return {
        "id": doc_id,
        "project": project,
        "slug": slug,
        "type": type,
        "content": content,
        "confidence": confidence,
        "extraction_method": extraction_method,
    }


@mcp.tool
def memory_get_document(slug: str) -> dict | None:
    project = config.get_project()
    return _get_service().get_document(project, slug)


@mcp.tool
def memory_get_latest(type: str) -> dict | None:
    project = config.get_project()
    config.validate_type(type)
    return _get_service().get_latest(project, type)


@mcp.tool
def memory_register_project(name: str) -> dict:
    name = name.strip()
    if not name:
        raise ValueError("project name must not be empty")
    cwd = Path.cwd()
    registry.register(cwd, name)
    return {"registered": str(cwd.resolve()), "project": name}


@mcp.tool
def memory_dashboard_graph(
    project: str | None = None,
    cross_project: bool = False,
    k: int = graph_cli.K_NEIGHBORS,
    min_similarity: float = graph_cli.MIN_SIMILARITY,
) -> dict:
    records = _get_service().get_all_with_vectors(project=project)
    return graph_cli._build_graph_data(
        records,
        k=k,
        cross_project=cross_project,
        min_similarity=min_similarity,
        current_project=project,
    )


@mcp.tool
def memory_dashboard_snapshot() -> dict:
    return dashboard.build_snapshot(_get_service())


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
