import argparse
import sys

from chronicle import config


def reindex(service, embed, project: str | None = None, say=print) -> int:
    """(Re)build the derived vector index from the SQLite memories."""
    rows = [row for row in service.repository.all(project) if row.status != "deleted"]
    for done, row in enumerate(rows, start=1):
        service.vector_index.upsert(row.id, embed(row.content), {"project": row.project, "type": row.type})
        if done % 25 == 0 or done == len(rows):
            say(f"Indexed {done}/{len(rows)} memories...")
    return len(rows)


def _reindex_main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog="chronicle reindex",
        description="Rebuild the semantic (vector) index from the SQLite memories.",
    )
    parser.add_argument("--project", default=None, help="only this project (default: all)")
    args = parser.parse_args(argv)
    if not config.semantic_enabled():
        raise SystemExit("chronicle reindex: semantic search is off. Run `chronicle semantic enable` first.")

    from chronicle import embeddings, services
    from chronicle.core.runtime import get_runtime

    services.ensure_qdrant()
    print("Embedding memories (the first run downloads the ~500MB model)...", flush=True)
    count = reindex(get_runtime(), embeddings.embed_text, args.project, say=lambda m: print(m, flush=True))
    print(f"Reindexed {count} memories.")


def _enable() -> None:
    from chronicle import embeddings, services

    try:
        embeddings.require_semantic_deps()
    except RuntimeError as error:
        raise SystemExit(f"chronicle semantic enable: {error}") from None
    services.ensure_qdrant()
    config.set_semantic(True)
    print("Semantic search: on. Indexing existing memories...", flush=True)
    _reindex_main([])
    print("Restart open Claude Code/Cursor/Codex/Claude Desktop sessions so they pick it up.")


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="chronicle semantic")
    parser.add_argument("action", choices=("enable", "disable", "status"))
    args = parser.parse_args(argv)
    if args.action == "enable":
        _enable()
    elif args.action == "disable":
        config.set_semantic(False)
        print("Semantic search: off (keyword search only). Qdrant data is untouched.")
        print("Restart open agent sessions so they pick it up.")
    else:
        state = "on (Qdrant + embedding model)" if config.semantic_enabled() else "off (keyword search only)"
        print(f"Semantic search: {state}")


def reindex_main(argv: list[str]) -> None:
    _reindex_main(argv)


if __name__ == "__main__":
    main(sys.argv[1:])
