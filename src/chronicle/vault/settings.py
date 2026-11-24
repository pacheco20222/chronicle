from pathlib import Path

from chronicle import config
from chronicle.vault.paths import chronicle_root


def vault_path() -> Path | None:
    path = config.read_config().get("vault_path")
    return Path(path).expanduser().resolve() if path else None


def set_vault_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == Path.home().resolve() or resolved == Path(resolved.anchor):
        raise ValueError(f"refusing vault {resolved}: home/root is not a vault folder")
    chronicle_root(resolved).mkdir(parents=True, exist_ok=True)
    data = config.read_config()
    data["vault_path"] = str(resolved)
    config.write_config(data)
    return resolved


def vault_projects() -> list[str]:
    projects = config.read_config().get("vault_projects", [])
    return projects if isinstance(projects, list) and all(isinstance(p, str) for p in projects) else []


def add_project(name: str) -> None:
    data = config.read_config()
    projects = data.setdefault("vault_projects", [])
    if name not in projects:
        projects.append(name)
        config.write_config(data)


def remove_project(name: str) -> None:
    data = config.read_config()
    projects = data.get("vault_projects", [])
    if name in projects:
        projects.remove(name)
        config.write_config(data)


def similarity_links() -> bool:
    return bool(config.read_config().get("vault_similarity_links", False))


def is_mirrored(project: str) -> bool:
    return vault_path() is not None and project in vault_projects()
