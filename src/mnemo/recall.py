import os
from pathlib import Path

from mnemo import config, registry, store


def latest_checkpoint(project: str) -> str | None:
    try:
        client = store.get_client()
        record = store.get_latest(client, project, "checkpoint")
    except Exception:
        # Deliberately fail open: a down Qdrant must never block session
        # start. Unlike config.get_project(), this isn't a security
        # boundary, just a best-effort convenience lookup.
        return None
    if record is None:
        return None
    return (
        f"[Mnemo] LATEST CHECKPOINT (saved {record['created_at']}) — the most recent "
        f"saved state for this project. Treat this as the answer to \"what is the "
        f"latest checkpoint\" and resume from it:\n{record['content']}"
    )


def overview_document(project: str) -> str | None:
    try:
        client = store.get_client()
        record = store.get_document(client, project, project)
    except Exception:
        # Same fail-open rationale as latest_checkpoint.
        return None
    if record is None:
        return None
    return (
        f"[Mnemo] Project overview — background reference only, NOT a checkpoint "
        f"(updated {record['updated_at']}):\n{record['content']}"
    )


def main() -> None:
    project = os.environ.get("MNEMO_PROJECT", "").strip()
    if not project:
        try:
            project = registry.lookup(Path.cwd()) or ""
        except Exception:
            project = ""
    if not project:
        return
    checkpoint = latest_checkpoint(project)
    if checkpoint:
        print(checkpoint)
    overview = overview_document(project)
    if overview:
        print(overview)


if __name__ == "__main__":
    main()
