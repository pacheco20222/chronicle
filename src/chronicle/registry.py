import json
import os
import subprocess
from pathlib import Path


def registry_path() -> Path:
    override = os.environ.get("CHRONICLE_REGISTRY_PATH", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".chronicle" / "projects.json"


class RegistryError(Exception):
    """Raised when the registry file exists but can't be parsed as JSON."""


def _load(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise RegistryError(f"{path} exists but isn't valid JSON: {e}") from e


def register(cwd: Path, project: str) -> None:
    resolved = cwd.resolve()
    if resolved == Path.home().resolve() or resolved == Path(resolved.anchor):
        raise ValueError(
            f"refusing to register {resolved}: home/root is not a project "
            f"folder. cd into the project first."
        )
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _load(path)
    data[str(cwd.resolve())] = project
    path.write_text(json.dumps(data, indent=2, sort_keys=True))


def _main_worktree(cwd: Path) -> Path | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    common = Path(out.stdout.strip())
    return common.parent if common.name == ".git" else None


def lookup(cwd: Path) -> str | None:
    data = _load(registry_path())
    hit = data.get(str(cwd.resolve()))
    if hit:
        return hit
    main = _main_worktree(cwd)
    if main is not None:
        return data.get(str(main.resolve()))
    return None


def list_projects() -> dict[str, list[str]]:
    projects: dict[str, list[str]] = {}
    for path, project in _load(registry_path()).items():
        projects.setdefault(project, []).append(path)
    return {project: sorted(paths) for project, paths in sorted(projects.items())}
