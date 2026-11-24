import json
import os
import tempfile
from pathlib import Path

from chronicle import project_resolution

QDRANT_URL = os.environ.get("CHRONICLE_QDRANT_URL", "http://localhost:6333")
SQLITE_PATH = Path(os.environ.get("CHRONICLE_SQLITE_PATH", Path.home() / ".chronicle" / "chronicle.db")).expanduser()
CONFIG_PATH = Path(os.environ.get("CHRONICLE_CONFIG_PATH", Path.home() / ".chronicle" / "config.json")).expanduser()
EMBED_MODEL = "nomic-ai/nomic-embed-text-v1.5"
VECTOR_SIZE = 768
COLLECTION_NAME = os.environ.get("CHRONICLE_COLLECTION", "memories")
VALID_TYPES = frozenset({"decision", "architecture", "bug", "todo", "note", "checkpoint", "overview"})
VALID_STATUSES = frozenset({"active", "proposed", "resolved", "superseded", "expired", "deleted", "wrong"})
VALID_RELATION_TYPES = frozenset({"related_to", "supersedes", "caused_by", "blocked_by", "implements", "relates_to_project"})


def semantic_enabled() -> bool:
    """Whether Qdrant + the embedding model are used (hybrid search). Off by
    default: CHRONICLE_SEMANTIC=1/0 wins, else `semantic` in config.json."""
    env = os.environ.get("CHRONICLE_SEMANTIC", "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    if env in ("0", "false", "no", "off"):
        return False
    return bool(read_config().get("semantic", False))


def read_config() -> dict:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_config(data: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=CONFIG_PATH.parent, delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(data, indent=2) + "\n")
        os.replace(temporary, CONFIG_PATH)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def set_semantic(enabled: bool) -> None:
    data = read_config()
    data["semantic"] = enabled
    write_config(data)


def get_project() -> str:
    return project_resolution.resolve(Path.cwd()).project


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
