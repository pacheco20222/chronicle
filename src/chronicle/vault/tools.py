"""Thin MCP adapters for vault configuration, jobs, and file discovery."""

from dataclasses import asdict

from fastmcp.exceptions import ToolError

from chronicle import config, refresh, registry
from chronicle.vault import catalog
from chronicle.vault.mirror import mirror_for


def _status(get_service) -> dict:
    return mirror_for(get_service()).status()


def _add(get_service, project: str) -> dict:
    result = mirror_for(get_service()).add_project(project)
    result.raise_for_error()
    return asdict(result)


def _remove(get_service, project: str) -> dict:
    mirror = mirror_for(get_service())
    deleted = mirror.remove_project(project)
    return {'project': project, 'deleted': deleted}


def _list_files(query: str | None, scope_path: str | None, limit: int) -> dict:
    if not 0 <= limit <= 2000:
        raise ValueError('limit must be between 0 and 2000')
    project = scope_path if scope_path is not None else config.get_project()
    entries, truncated = catalog.list_files(project, query, limit=limit)
    files = [{'folder': entry.folder, 'path': entry.relative_path,
              'absolute_path': entry.absolute_path, 'size': entry.size,
              'modified': entry.modified} for entry in entries]
    return {'project': project, 'files': files, 'truncated': truncated}


def _call(function, *args) -> dict:
    try:
        return function(*args)
    except (ValueError, OSError, RuntimeError, registry.RegistryError) as error:
        raise ToolError(str(error)) from None


def register(mcp, get_service) -> None:
    @mcp.tool
    def memory_vault_status() -> dict:
        """Show the configured vault, opted-in projects, and mirror diagnostics."""
        return _call(_status, get_service)

    @mcp.tool
    def memory_vault_add_project(project: str) -> dict:
        """Opt in and sync an existing project, only when the user asks."""
        return _call(_add, get_service, project)

    @mcp.tool
    def memory_vault_remove_project(project: str) -> dict:
        """Opt out and delete generated project pages, only when the user asks."""
        return _call(_remove, get_service, project)

    @mcp.tool
    def memory_vault_sync(project: str | None = None) -> dict:
        """Start a vault sync, or return the currently running job's progress."""
        return _call(refresh.start_vault_sync, get_service(), project)

    @mcp.tool
    def memory_list_files(
        query: str | None = None, scope_path: str | None = None, limit: int = 200,
    ) -> dict:
        """Find documents in this project's registered folders without requiring a vault."""
        return _call(_list_files, query, scope_path, limit)
