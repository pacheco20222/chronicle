import os
from pathlib import Path

from mnemo import registry

QDRANT_URL = os.environ.get("MNEMO_QDRANT_URL", "http://localhost:6333")
EMBED_MODEL = "nomic-ai/nomic-embed-text-v1.5"
VECTOR_SIZE = 768
COLLECTION_NAME = os.environ.get("MNEMO_COLLECTION", "memories")
VALID_TYPES = frozenset({"decision", "architecture", "bug", "todo", "note", "checkpoint", "overview"})
VALID_STATUSES = frozenset({"active", "resolved", "superseded"})


def get_project() -> str:
    project = os.environ.get("MNEMO_PROJECT", "").strip()
    if project:
        return project
    try:
        registered = registry.lookup(Path.cwd())
    except registry.RegistryError as e:
        raise RuntimeError(
            f"MNEMO_PROJECT is not set, and the folder registry couldn't "
            f"be read: {e}. Fix or delete the file and re-register this "
            f"folder."
        ) from e
    if registered:
        return registered
    raise RuntimeError(
        "MNEMO_PROJECT is not set and this folder isn't registered. Ask "
        "Claude to register this folder as a project "
        "(memory_register_project), or run `mnemo register --project X` "
        "yourself."
    )


def validate_type(type_: str) -> None:
    if type_ not in VALID_TYPES:
        raise ValueError(f"invalid type {type_!r}, must be one of {sorted(VALID_TYPES)}")


def validate_status(status: str) -> None:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status {status!r}, must be one of {sorted(VALID_STATUSES)}")
