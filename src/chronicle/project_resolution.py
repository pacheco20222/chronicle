import os
from dataclasses import dataclass
from pathlib import Path

from chronicle import registry

_pending_notice: str | None = None


class ProjectNotFoundError(RuntimeError):
    """Raised with guidance when a request's project cannot be resolved."""


@dataclass(frozen=True)
class Resolution:
    project: str
    registered_now: bool


def resolve(cwd: Path) -> Resolution:
    global _pending_notice

    project = os.environ.get("CHRONICLE_PROJECT", "").strip()
    if project:
        return Resolution(project, False)
    try:
        registered = registry.lookup(cwd)
    except registry.RegistryError as e:
        raise ProjectNotFoundError(
            f"CHRONICLE_PROJECT is not set, and the folder registry couldn't "
            f"be read: {e}. Fix or delete the file and re-register this "
            f"folder."
        ) from e
    if registered:
        return Resolution(registered, False)

    root = registry.main_worktree(cwd)
    if root is not None and root.resolve() not in (
        Path.home().resolve(), Path(root.anchor),
    ):
        paths = registry.list_projects().get(root.name, [])
        other_paths = [path for path in paths if Path(path).resolve() != root.resolve()]
        if other_paths:
            raise ProjectNotFoundError(
                f"Project name '{root.name}' is already used by {other_paths[0]}. "
                "Please ask the user for a different name, then call memory_register_project(name)."
            )
        try:
            from chronicle import config
            from chronicle.core.repository import MemoryRepository
            from chronicle.storage.database import Database

            database = Database(config.sqlite_url())
            try:
                project_exists = MemoryRepository(database).project_exists(root.name)
            finally:
                database.engine.dispose()
        except Exception as e:
            raise ProjectNotFoundError(
                f"Could not check storage for project '{root.name}': {e}. "
                "Automatic registration refused; restore storage access and try again."
            ) from e
        if project_exists:
            raise ProjectNotFoundError(
                f"Project '{root.name}' already has memories. Please ask the user "
                "whether this folder belongs to that project or should use a different name. "
                f"If it belongs, call memory_register_project('{root.name}')."
            )
        registry.register(root, root.name)
        _pending_notice = (
            f"Registered {root} as Chronicle project '{root.name}' (git repo, automatic)."
        )
        return Resolution(root.name, True)

    raise ProjectNotFoundError(
        "CHRONICLE_PROJECT is not set and this folder isn't registered. "
        "For a folder client, ask the user which project to use, then call "
        "memory_register_project, or run `chronicle register --project X`. "
        "For a client without a project folder, use memory_list_scopes and "
        "pass scope_path explicitly."
    )


def take_registration_notice() -> str | None:
    global _pending_notice
    notice = _pending_notice
    _pending_notice = None
    return notice
