"""User-level setup for every installed MCP client, without a pinned project."""

import json
import shlex
import shutil
import subprocess
from pathlib import Path

from chronicle import setup_cli


def _add_cli(app: str, command: list[str], dry_run: bool) -> str:
    if dry_run:
        return shlex.join(command)
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        return f"chronicle setup: `{app} mcp add` failed (see above)."
    return f"Set up Chronicle for {app}."


def setup_global(dry_run: bool, hook: bool) -> list[str]:
    """Return status lines after configuring installed apps in discovery order."""
    install_dir = Path(setup_cli.__file__).resolve().parents[2]
    entry = setup_cli._server_entry(None, install_dir)
    if entry["command"] == "uv":
        entry["command"] = Path(shutil.which("uv") or "uv").as_posix()
    command = [entry["command"], *entry["args"]]
    home = Path.home()
    lines = []

    if shutil.which("claude"):
        lines.append(_add_cli("claude", ["claude", "mcp", "add", "--scope", "user", "chronicle", "--", *command], dry_run))
        if hook:
            lines.append(setup_cli._merge_hook(
                home / ".claude" / "settings.json",
                setup_cli._recall_hook_command(None, install_dir), dry_run,
            ))
    else:
        lines.append("skipped: Claude Code not found")

    if (home / ".cursor").is_dir():
        lines.append(setup_cli._merge_server(home / ".cursor" / "mcp.json", "chronicle", entry, dry_run))
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
        lines.append(setup_cli._merge_server(desktop_path, "chronicle", entry, dry_run))
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
