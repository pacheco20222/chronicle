import os
from pathlib import Path

from chronicle import registry

QDRANT_URL = os.environ.get("CHRONICLE_QDRANT_URL", "http://localhost:6333")
SQLITE_PATH = Path(os.environ.get("CHRONICLE_SQLITE_PATH", Path.home() / ".chronicle" / "chronicle.db")).expanduser()
EMBED_MODEL = "nomic-ai/nomic-embed-text-v1.5"
VECTOR_SIZE = 768
COLLECTION_NAME = os.environ.get("CHRONICLE_COLLECTION", "memories")
VALID_TYPES = frozenset({"decision", "architecture", "bug", "todo", "note", "checkpoint", "overview"})
VALID_STATUSES = frozenset({"active", "proposed", "resolved", "superseded", "expired", "deleted", "wrong"})
VALID_RELATION_TYPES = frozenset({"related_to", "supersedes", "caused_by", "blocked_by", "implements"})


def get_project() -> str:
    project = os.environ.get("CHRONICLE_PROJECT", "").strip()
    if project:
        return project
    try:
        registered = registry.lookup(Path.cwd())
    except registry.RegistryError as e:
        raise RuntimeError(
            f"CHRONICLE_PROJECT is not set, and the folder registry couldn't "
            f"be read: {e}. Fix or delete the file and re-register this "
            f"folder."
        ) from e
    if registered:
        return registered
    raise RuntimeError(
        "CHRONICLE_PROJECT is not set and this folder isn't registered. Ask "
        "Claude to register this folder as a project "
        "(memory_register_project), or run `chronicle register --project X` "
        "yourself."
    )


def sqlite_url() -> str:
    return f"sqlite:///{SQLITE_PATH}"


def validate_type(type_: str) -> None:
    if type_ not in VALID_TYPES:
        raise ValueError(f"invalid type {type_!r}, must be one of {sorted(VALID_TYPES)}")


def validate_status(status: str) -> None:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status {status!r}, must be one of {sorted(VALID_STATUSES)}")


def validate_relation_type(relation_type: str) -> None:
    if relation_type not in VALID_RELATION_TYPES:
        raise ValueError(
            f"invalid relation type {relation_type!r}, must be one of {sorted(VALID_RELATION_TYPES)}"
        )
