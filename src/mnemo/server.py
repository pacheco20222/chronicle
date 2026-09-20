from pathlib import Path

from fastmcp import FastMCP

from mnemo import config, embeddings, registry, store

mcp = FastMCP(
    "mnemo",
    instructions=(
        "This server stores project-scoped memories. When the user asks to "
        "checkpoint progress (e.g. says \"checkpoint this\" or asks to save "
        "where things stand before clearing the session), call memory_add "
        "with type=\"checkpoint\" and content summarizing: the current "
        "state, what's been tried (including things that did NOT work), "
        "and the concrete next step. Write it so that someone with zero "
        "memory of this conversation could resume the work from it alone. "
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
        "type, k), which searches across every project, not just this "
        "one. Only call it when the user explicitly asks for something "
        "cross-project (e.g. \"what have I done across all my "
        "projects\") — never as a fallback or default when the normal "
        "memory_search, scoped to this project, would do. If any memory "
        "tool call fails because no project is set for this folder, or "
        "the user explicitly asks to set up Mnemo here, call "
        "memory_register_project(name) with a short project id — it "
        "registers the current folder so every future call in it "
        "resolves automatically, immediately, no restart needed. Beyond "
        "explicit requests: if you notice a change worth reflecting in "
        "the project overview document, ask before updating it — don't "
        "update it silently. Separately, if a while has passed without "
        "saving anything and something notable has come up, ask whether "
        "to save it as a note — never save either one automatically."
    ),
)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = store.get_client()
        store.ensure_collection(_client)
    return _client


@mcp.tool
def memory_add(content: str, type: str) -> dict:
    project = config.get_project()
    config.validate_type(type)
    vector = embeddings.embed_text(content)
    memory_id = store.add_memory(_get_client(), vector, content, project, type)
    return {"id": memory_id, "project": project, "type": type, "content": content}


@mcp.tool
def memory_search(query: str, type: str | None = None, k: int = 5) -> list[dict]:
    project = config.get_project()
    if type == "checkpoint":
        # Checkpoints are a timeline, not a topic: newest first, query ignored.
        return store.get_recent(_get_client(), project, "checkpoint", k=k)
    vector = embeddings.embed_text(query)
    return store.search_memory(_get_client(), vector, project, type_=type, k=k)


@mcp.tool
def memory_search_global(query: str, type: str | None = None, k: int = 5) -> list[dict]:
    vector = embeddings.embed_text(query)
    return store.search_memory_global(_get_client(), vector, type_=type, k=k)


@mcp.tool
def memory_set_document(slug: str, content: str, type: str) -> dict:
    project = config.get_project()
    config.validate_type(type)
    vector = embeddings.embed_text(content)
    doc_id = store.set_document(_get_client(), vector, content, project, slug, type)
    return {"id": doc_id, "project": project, "slug": slug, "type": type, "content": content}


@mcp.tool
def memory_get_document(slug: str) -> dict | None:
    project = config.get_project()
    return store.get_document(_get_client(), project, slug)


@mcp.tool
def memory_get_latest(type: str) -> dict | None:
    project = config.get_project()
    config.validate_type(type)
    return store.get_latest(_get_client(), project, type)


@mcp.tool
def memory_register_project(name: str) -> dict:
    name = name.strip()
    if not name:
        raise ValueError("project name must not be empty")
    cwd = Path.cwd()
    registry.register(cwd, name)
    return {"registered": str(cwd.resolve()), "project": name}


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
