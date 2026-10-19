import argparse
import base64
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from chronicle import registry

AGENTS = ("claude-desktop", "claude-code", "cursor", "codex")


def _powershell_quote(value: str) -> str:
    """Quote a value as a PowerShell single-quoted string literal.

    Single-quoted PowerShell strings have exactly one escaping rule —
    double an embedded `'` — so this is correct wherever the result is
    used, with no separate "nested" mode needed.
    """
    return "'" + value.replace("'", "''") + "'"


def _chronicle_exe() -> str | None:
    """Absolute path of the installed `chronicle` command, if it is on PATH."""
    found = shutil.which("chronicle")
    return Path(found).resolve().as_posix() if found else None


def _server_entry(project: str, install_dir: Path) -> dict:
    """One `mcpServers` entry. Prefers the installed `chronicle` command and
    falls back to `uv --directory <clone> run chronicle`."""
    env = {"CHRONICLE_PROJECT": project}
    exe = _chronicle_exe()
    if exe:
        return {"command": exe, "args": [], "env": env}
    return {
        "command": "uv",
        "args": ["--directory", install_dir.as_posix() if sys.platform == "win32" else str(install_dir), "run", "chronicle"],
        "env": env,
    }


def _desktop_config_path() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(appdata) / "Claude" / "claude_desktop_config.json"
    raise SystemExit("chronicle setup: Claude Desktop is only available on macOS and Windows.")


def _write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _backup(path: Path) -> None:
    """Copy `path` to `<path>.bak` without following a pre-planted symlink."""
    bak = path.with_name(path.name + ".bak")
    bak.unlink(missing_ok=True)
    shutil.copyfile(path, bak)


def _inside_cwd(path: Path) -> Path:
    """Refuse repo-scoped config paths that symlink outside the current folder."""
    if not path.resolve().is_relative_to(Path.cwd().resolve()):
        raise SystemExit(
            f"chronicle setup: {path} resolves outside the current folder "
            "(symlink?); nothing was changed."
        )
    return path


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        config = json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError as error:
        raise SystemExit(
            f"chronicle setup: {path} is not valid JSON ({error}). Fix it "
            "first; nothing was changed."
        ) from None
    if not isinstance(config, dict):
        raise SystemExit(f"chronicle setup: {path} has an unexpected shape; nothing was changed.")
    return config


def _merge_server(path: Path, key: str, entry: dict, dry_run: bool) -> str:
    """Add `entry` under mcpServers[key] without touching anything else."""
    existed = path.exists()
    config = _read_json(path)
    if not isinstance(config.get("mcpServers", {}), dict):
        raise SystemExit(f"chronicle setup: {path} has an unexpected shape; nothing was changed.")
    servers = config.setdefault("mcpServers", {})
    if servers.get(key) == entry:
        return f"Already set up: '{key}' in {path} is unchanged."
    verb = "Updated" if key in servers else "Added"
    servers[key] = entry
    if dry_run:
        return f"Would write to {path}:\n{json.dumps({'mcpServers': {key: entry}}, indent=2)}"
    if existed:
        _backup(path)
    _write_json_atomic(path, config)
    backup = f" (previous file saved as {path.name}.bak)" if existed else ""
    return f"{verb} '{key}' in {path}{backup}."


def _recall_hook_command(project: str, install_dir: Path) -> str:
    """SessionStart command that prints the latest checkpoint and overview."""
    exe = _chronicle_exe()
    recall = None
    if exe:
        sibling = Path(exe).with_name("chronicle-recall" + (".exe" if sys.platform == "win32" else ""))
        recall = sibling.as_posix() if sibling.exists() else None
    if sys.platform == "win32":
        run = f"& {_powershell_quote(recall)}" if recall else f"uv run --directory {_powershell_quote(install_dir.as_posix())} chronicle-recall"
        script = f"$env:CHRONICLE_PROJECT={_powershell_quote(project)}; {run}"
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        return f"powershell.exe -NoProfile -EncodedCommand {encoded}"
    run = shlex.quote(recall) if recall else f"uv run --directory {shlex.quote(str(install_dir))} chronicle-recall"
    return f"CHRONICLE_PROJECT={shlex.quote(project)} {run}"


def _merge_hook(path: Path, command: str, dry_run: bool) -> str:
    """Add the recall hook to a Claude Code settings file, replacing any
    earlier chronicle-recall hook instead of duplicating it."""
    config = _read_json(path)
    groups = config.setdefault("hooks", {}).setdefault("SessionStart", [])
    for group in groups:
        group["hooks"] = [h for h in group.get("hooks", []) if not _is_recall_hook(h)]
    groups[:] = [g for g in groups if g.get("hooks")]
    groups.append({"matcher": "startup|resume|clear", "hooks": [{"type": "command", "command": command}]})
    if dry_run:
        return f"Would add this SessionStart hook to {path}:\n{command}"
    if path.exists():
        _backup(path)
    _write_json_atomic(path, config)
    return f"Set the session-start recall hook in {path}."


def _is_recall_hook(hook: dict) -> bool:
    command = hook.get("command", "")
    if "chronicle-recall" in command:
        return True
    # Windows hooks are base64 PowerShell: decode to look for the script name
    if "-EncodedCommand " in command:
        try:
            decoded = base64.b64decode(command.split("-EncodedCommand ", 1)[1]).decode("utf-16le")
        except Exception:
            return False
        return "chronicle-recall" in decoded
    return False


def _setup_agent(agent: str, project: str | None, dry_run: bool, hook: bool = True) -> None:
    if not project:
        raise SystemExit(f"chronicle setup {agent}: --project NAME is required.")
    install_dir = Path(__file__).resolve().parents[2]
    entry = _server_entry(project, install_dir)
    if entry["command"] == "uv":
        # GUI apps (Claude Desktop) don't see the shell PATH, so pin uv's path
        entry["command"] = Path(shutil.which("uv") or "uv").as_posix()

    if agent == "claude-desktop":
        # one entry per project: Desktop chat has no folder to infer it from
        print(_merge_server(_desktop_config_path(), f"chronicle-{project}", entry, dry_run))
        if not dry_run:
            print("Fully quit Claude Desktop (Cmd+Q / tray > Quit) and reopen it, then start a new chat.")
        return
    if agent in ("claude-code", "cursor"):
        path = _inside_cwd(Path.cwd() / (".mcp.json" if agent == "claude-code" else ".cursor/mcp.json"))
        print(_merge_server(path, "chronicle", entry, dry_run))
        if agent == "claude-code" and hook:
            command = _recall_hook_command(project, install_dir)
            print(_merge_hook(_inside_cwd(Path.cwd() / ".claude" / "settings.json"), command, dry_run))
        return

    # codex: one server entry for every project, then register this folder
    command = [entry["command"], *entry["args"]]
    codex_cmd = ["codex", "mcp", "add", "chronicle", "--", *command]
    if dry_run or shutil.which("codex") is None:
        print("Run this once, ever:\n" + shlex.join(codex_cmd))
    else:
        result = subprocess.run(codex_cmd, check=False)
        if result.returncode != 0:
            raise SystemExit("chronicle setup: `codex mcp add` failed (see above); the folder was not registered.")
    if not dry_run:
        try:
            registry.register(Path.cwd(), project)
        except registry.AlreadyRegisteredError as error:
            raise SystemExit(f"chronicle setup: {error}") from None
        print(f"Registered {Path.cwd().resolve()} as project '{project}'.")


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="chronicle setup")
    parser.add_argument(
        "agent",
        nargs="?",
        choices=AGENTS,
        help="write the MCP config for this agent (omit to just print every option)",
    )
    parser.add_argument("--project", default=None)
    parser.add_argument("--no-hook", dest="hook", action="store_false", help="claude-code: skip the session-start recall hook")
    parser.add_argument("--print", dest="dry_run", action="store_true", help="show what would be written; change nothing")
    args = parser.parse_args(argv)

    if args.agent:
        _setup_agent(args.agent, args.project, args.dry_run, args.hook)
        return

    install_dir = Path(__file__).resolve().parents[2]
    project = args.project or "your-project-name"

    if sys.platform == "win32":
        install_path = install_dir.as_posix()
        ps_script = (
            f"$env:CHRONICLE_PROJECT={_powershell_quote(project)}; "
            f"uv run --directory {_powershell_quote(install_path)} chronicle-recall"
        )
        encoded_script = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")
        hook_command = f"powershell.exe -NoProfile -EncodedCommand {encoded_script}"
        codex_cmd = (
            "codex mcp add chronicle -- "
            f"uv run --project {_powershell_quote(install_path)} chronicle"
        )
        register_cmd = (
            f"uv run --project {_powershell_quote(install_path)} "
            f"chronicle register --project {_powershell_quote(project)}"
        )
    else:
        install_path = str(install_dir)
        hook_command = (
            f"CHRONICLE_PROJECT={shlex.quote(project)} "
            f"uv run --directory {shlex.quote(install_path)} chronicle-recall"
        )
        codex_cmd = f"codex mcp add chronicle -- uv run --project {shlex.quote(install_path)} chronicle"
        register_cmd = (
            f"uv run --project {shlex.quote(install_path)} "
            f"chronicle register --project {shlex.quote(project)}"
        )

    mcp_config = {"mcpServers": {"chronicle": _server_entry(project, install_dir)}}
    hook_config = {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "startup|resume|clear",
                    "hooks": [{"type": "command", "command": hook_command}],
                }
            ]
        }
    }
    mcp_json = json.dumps(mcp_config, indent=2)
    hook_json = json.dumps(hook_config, indent=2)

    print("Add this to your repo's .mcp.json (Claude Code):\n")
    print(mcp_json)
    print("\nOptional — add this to your repo's .claude/settings.json to auto-load checkpoints and documents every session:\n")
    print(hook_json)
    print("\nFor Cursor, add the same block to your repo's .cursor/mcp.json instead (identical format, different file):\n")
    print(mcp_json)
    print(
        "\nFor Codex, this is two separate steps, not one command per "
        "project. First, run this once, ever — never re-run it for "
        "another project:\n"
    )
    print(codex_cmd)
    print(
        "\nThen, for EVERY project folder you want memory in, register it "
        "(once per folder, from inside that folder) — skip this if you "
        "already registered it via Claude Code's /chronicle:chronicle-register, "
        "same shared registry:\n"
    )
    print(f"cd /path/to/your-project && {register_cmd}")
    if sys.platform == "win32":
        print("\n(Run this from PowerShell, not cmd.exe — the quoting above assumes it.)")
    if args.project is None:
        print(
            "\n(Replace 'your-project-name' with your actual project id in "
            "the .mcp.json/.cursor/mcp.json/hook blocks above, or re-run "
            "with --project NAME — this doesn't apply to the Codex command, "
            "which has no project baked in.)"
        )
