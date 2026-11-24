"""The one background job behind the dashboard's "Add project" and
"Update all projects" buttons, with progress to poll.

Also run when the dashboard starts. Only one job runs at a time. Also lists
folders for the "Add project" picker.
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


class JobBusyError(RuntimeError):
    pass


def _claim() -> dict | None:
    """Mark a job as running; None when one already is."""
    with _lock:
        if _state["status"] == "running":
            return None
        _state.update(_IDLE, status="running")
        return dict(_state)


def _launch(work) -> dict:
    snapshot = _claim()
    if snapshot is None:
        return status()
    _spawn(work)
    return snapshot


def _spawn(work) -> None:
    def run() -> None:
        try:
            work()
            _set(status="done")
        except Exception as error:  # a thread: report, never crash the server
            _set(status="error", error=f"{type(error).__name__}: {error}")

    threading.Thread(target=run, name="chronicle-refresh", daemon=True).start()


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
    # Claim before registering: if another job runs, refuse rather than
    # register the folder and silently skip its import.
    snapshot = _claim()
    if snapshot is None:
        raise JobBusyError("another refresh is already running; try again when it finishes")
    try:
        registry.register(path, project)  # raises on home/root or a name clash
    except Exception:
        _set(**_IDLE)
        raise

    def work() -> None:
        import_cli.import_directory(
            service, str(path.resolve()), project, type_, progress=_progress("Reading documents")
        )

    _spawn(work)
    return snapshot


def list_folders(path: str | None = None) -> dict:
    """Visible sub-folders of `path` (the home folder when omitted) and its parent."""
    here = (Path(path).expanduser() if path else Path.home()).resolve()
    if not here.is_dir():
        raise ValueError(f"{path} is not a folder")
    try:
        names = sorted(
            (entry.name for entry in here.iterdir() if not entry.name.startswith(".") and entry.is_dir()),
            key=str.lower,
        )
    except OSError:  # unreadable folder: show it as empty rather than failing the picker
        names = []
    parent = None if here == Path(here.anchor) else str(here.parent)
    return {"path": str(here), "parent": parent, "folders": names}


def start_vault_sync(service, project: str | None = None) -> dict:
    """Rebuild vault pages through the shared single-job slot."""
    from chronicle.vault import settings
    from chronicle.vault.mirror import mirror_for

    snapshot = _claim()
    if snapshot is None:
        return status()
    try:
        mirror = mirror_for(service)
        projects = [project] if project is not None else settings.vault_projects()
        if project is not None:
            mirror.require_mirrored(project)
        _set(label="Syncing vault", done=0, total=len(projects))
        snapshot = status()

        def work() -> None:
            for done, name in enumerate(projects, 1):
                mirror.sync_project(name).raise_for_error()
                _set(done=done, total=len(projects))

        _spawn(work)
    except Exception as error:
        _set(status="error", error=f"{type(error).__name__}: {error}")
        raise
    return snapshot
