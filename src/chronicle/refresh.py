"""The one background job behind the dashboard's "Add project" and
"Update all projects" buttons, with progress to poll.

Also run when the dashboard starts. Only one job runs at a time.
"""

import threading
from pathlib import Path

from chronicle import config, import_cli, registry, semantic_cli

_IDLE = {"status": "idle", "label": "", "done": 0, "total": 0, "error": None}
_lock = threading.Lock()
_state: dict = dict(_IDLE)


def status() -> dict:
    with _lock:
        return dict(_state)


def _set(**changes) -> None:
    with _lock:
        _state.update(changes)


def _progress(label: str):
    _set(label=label, done=0, total=0)
    return lambda done, total: _set(done=done, total=total)


def _launch(work) -> dict:
    with _lock:
        if _state["status"] == "running":
            return dict(_state)
        _state.update(_IDLE, status="running")
        snapshot = dict(_state)

    def run() -> None:
        try:
            work()
            _set(status="done")
        except Exception as error:  # a thread: report, never crash the server
            _set(status="error", error=f"{type(error).__name__}: {error}")

    threading.Thread(target=run, name="chronicle-refresh", daemon=True).start()
    return snapshot


def start(service) -> dict:
    """Re-embed every project's memories (needs semantic search)."""
    if not config.semantic_enabled():
        raise RuntimeError("semantic search is off, so there is no similarity index to refresh")

    def work() -> None:
        from chronicle import embeddings

        semantic_cli.reindex(
            service,
            embeddings.embed_text,
            say=lambda message: None,
            progress=_progress("Re-embedding memories"),
        )

    return _launch(work)


def add_project(service, folder: str, project: str, type_: str) -> dict:
    """Register `folder` as `project` and import its .md/.txt files as memories.

    Adding the same folder again re-scans it: only changed or new files import.
    """
    path = Path(folder).expanduser()
    if not path.is_dir():
        raise ValueError(f"{folder} is not a folder")
    project = project.strip()
    if not project:
        raise ValueError("a project name is required")
    config.validate_type(type_)
    registry.register(path, project)  # raises on home/root or a name clash

    def work() -> None:
        import_cli.import_directory(
            service, str(path.resolve()), project, type_, progress=_progress("Reading documents")
        )

    return _launch(work)
