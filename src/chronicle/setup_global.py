"""User-level setup for every installed MCP client, without a pinned project."""

import json
import shlex
import shutil
import subprocess
from pathlib import Path

from chronicle import setup_cli


def _clone_executable(install_dir: Path, name: str) -> str:
    directory, suffix = ("Scripts", ".exe") if setup_cli.sys.platform == "win32" else ("bin", "")
    executable = install_dir / ".venv" / directory / (name + suffix)
    if not executable.is_file():
        raise SystemExit(
            f"chronicle setup: {executable} is missing. Run `uv sync` in the clone "
            "or `uv tool install --editable .` first; nothing was changed."
        )
    return executable.as_posix()


def _add_cli(app: str, command: list[str], dry_run: bool) -> str:
    if dry_run:
        return shlex.join(command)
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        return f"chronicle setup: `{app} mcp add` failed (see above)."
    return f"Set up Chronicle for {app}."


def _merge_global_server(path: Path, entry: dict, dry_run: bool) -> str:
    config = setup_cli._read_json(path)
    servers = config.get("mcpServers", {})
    existing = servers.get("chronicle") if isinstance(servers, dict) else None
    env = existing.get("env") if isinstance(existing, dict) else None
    if isinstance(env, dict) and "CHRONICLE_PROJECT" in env:
        return (
            f"Skipped {path}: Chronicle is pinned to project '{env['CHRONICLE_PROJECT']}'. "
            "Remove env.CHRONICLE_PROJECT from mcpServers.chronicle, then rerun "
            "`chronicle setup --global` for global behavior."
        )
    return setup_cli._merge_server(path, "chronicle", entry, dry_run)


def setup_global(dry_run: bool, hook: bool) -> list[str]:
    """Return status lines after configuring installed apps in discovery order."""
    install_dir = Path(setup_cli.__file__).resolve().parents[2]
    entry = setup_cli._server_entry(None, install_dir)
    claude = shutil.which("claude")
    hook_command = setup_cli._recall_hook_command(None, install_dir) if claude and hook else None
    command = [entry["command"], *entry["args"]]
    home = Path.home()
    lines = []

    if claude:
        lines.append(_add_cli("claude", ["claude", "mcp", "add", "--scope", "user", "chronicle", "--", *command], dry_run))
        if hook:
            lines.append(setup_cli._merge_hook(
                home / ".claude" / "settings.json",
                hook_command, dry_run,
            ))
    else:
        lines.append("skipped: Claude Code not found")

    if (home / ".cursor").is_dir():
        lines.append(_merge_global_server(home / ".cursor" / "mcp.json", entry, dry_run))
    else:
        lines.append("skipped: Cursor not found")

    if shutil.which("codex"):
        lines.append(_add_cli("codex", ["codex", "mcp", "add", "chronicle", "--", *command], dry_run))
    else:
        lines.append("skipped: Codex not found")

    try:
        desktop_path = setup_cli._desktop_config_path()
    except SystemExit:
        desktop_path = None
    if desktop_path is not None and desktop_path.parent.is_dir():
        lines.append(_merge_global_server(desktop_path, entry, dry_run))
        if not dry_run:
            lines.append("Fully quit Claude Desktop (Cmd+Q / tray > Quit) and reopen it, then start a new chat.")
    else:
        lines.append("skipped: Claude Desktop not found")

    local_path = Path.cwd() / ".mcp.json"
    if local_path.is_file():
        try:
            local_config = json.loads(local_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            local_config = {}
        servers = local_config.get("mcpServers", {}) if isinstance(local_config, dict) else {}
        if isinstance(servers, dict) and "chronicle" in servers:
            lines.append(f"Warning: {local_path} also defines 'chronicle'; it may override user-level config.")
    return lines
