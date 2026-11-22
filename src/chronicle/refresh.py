"""One background job that re-embeds every memory, with progress to poll.

Shared by the dashboard's "Update all projects" button and the refresh that
runs when the dashboard starts. Only one job runs at a time.
"""

import threading

from chronicle import config, semantic_cli

_lock = threading.Lock()
_state: dict = {"status": "idle", "done": 0, "total": 0, "error": None}


def status() -> dict:
    with _lock:
        return dict(_state)


def _set(**changes) -> None:
    with _lock:
        _state.update(changes)


def _run(service) -> None:
    try:
        from chronicle import embeddings

        semantic_cli.reindex(
            service,
            embeddings.embed_text,
            say=lambda message: None,
            progress=lambda done, total: _set(done=done, total=total),
        )
        _set(status="done")
    except Exception as error:  # the job is a thread: report, never crash the server
        _set(status="error", error=f"{type(error).__name__}: {error}")


def start(service) -> dict:
    """Start refreshing every project; a no-op if a refresh is already running."""
    if not config.semantic_enabled():
        raise RuntimeError("semantic search is off, so there is no similarity index to refresh")
    with _lock:
        if _state["status"] == "running":
            return dict(_state)
        _state.update(status="running", done=0, total=0, error=None)
        snapshot = dict(_state)
    threading.Thread(target=_run, args=(service,), name="chronicle-refresh", daemon=True).start()
    return snapshot
