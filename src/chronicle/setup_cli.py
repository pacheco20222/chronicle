import argparse
import base64
import json
import shlex
import sys
from pathlib import Path


def _powershell_quote(value: str) -> str:
    """Quote a value as a PowerShell single-quoted string literal.

    Single-quoted PowerShell strings have exactly one escaping rule —
    double an embedded `'` — so this is correct wherever the result is
    used, with no separate "nested" mode needed.
    """
    return "'" + value.replace("'", "''") + "'"


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="chronicle setup")
    parser.add_argument("--project", default=None)
    args = parser.parse_args(argv)

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

    mcp_config = {
        "mcpServers": {
            "chronicle": {
                "command": "uv",
                "args": ["--directory", install_path, "run", "chronicle"],
                "env": {"CHRONICLE_PROJECT": project},
            }
        }
    }
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
