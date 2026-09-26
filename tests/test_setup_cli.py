import base64
import json
import subprocess
import sys

import pytest

from chronicle import setup_cli


def _printed_json_documents(out: str) -> tuple[dict, dict]:
    decoder = json.JSONDecoder()
    first_start = out.index("{")
    mcp_config, first_length = decoder.raw_decode(out[first_start:])
    second_start = out.index("{", first_start + first_length)
    hook_config, _ = decoder.raw_decode(out[second_start:])
    return mcp_config, hook_config


def _codex_command(out: str) -> str:
    return out.split("another project:\n\n", maxsplit=1)[1].splitlines()[0]


@pytest.mark.parametrize(
    ("value", "quoted"),
    [
        ("$", "'$'"),
        ("`", "'`'"),
        ("'", "''''"),
        ('"', "'\"'"),
        ("$`'\"", "'$`''\"'"),
    ],
)
def test_powershell_quote_doubles_single_quotes_only(value, quoted):
    assert setup_cli._powershell_quote(value) == quoted


@pytest.mark.skipif(sys.platform != "win32", reason="requires PowerShell")
def test_powershell_quote_round_trips_via_encoded_command():
    value = "$`'\"combined"
    command = f"[Console]::Out.Write({setup_cli._powershell_quote(value)})"
    encoded_command = base64.b64encode(command.encode("utf-16le")).decode("ascii")
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-EncodedCommand", encoded_command],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout == value, command


def test_setup_prints_mcp_json_and_codex_command(capsys):
    setup_cli.main(["--project", "myproj"])
    out = capsys.readouterr().out
    assert '"CHRONICLE_PROJECT": "myproj"' in out
    assert "codex mcp add chronicle --" in out
    assert "CHRONICLE_PROJECT" not in _codex_command(out)
    assert '"command": "uv"' in out


def test_setup_prints_cursor_block_matching_claude_code_block(capsys):
    setup_cli.main(["--project", "myproj"])
    out = capsys.readouterr().out
    assert "For Cursor, add the same block to your repo's .cursor/mcp.json" in out
    assert out.count('"CHRONICLE_PROJECT": "myproj"') == 2


def test_setup_uses_placeholder_when_no_project_given(capsys):
    setup_cli.main([])
    out = capsys.readouterr().out
    assert "your-project-name" in out


def test_setup_prints_session_start_hook_block(capsys):
    setup_cli.main(["--project", "myproj"])
    out = capsys.readouterr().out
    _, hook_config = _printed_json_documents(out)
    command = hook_config["hooks"]["SessionStart"][0]["hooks"][0]["command"]

    assert hook_config["hooks"]["SessionStart"][0]["matcher"] == "startup|resume|clear"
    if sys.platform == "win32":
        assert command.startswith("powershell.exe -NoProfile -EncodedCommand ")
        encoded = command.split("-EncodedCommand ", maxsplit=1)[1]
        script = base64.b64decode(encoded).decode("utf-16le")
        assert "CHRONICLE_PROJECT='myproj'" in script
        assert "chronicle-recall" in script
    else:
        assert "CHRONICLE_PROJECT=myproj uv run --directory" in command
        assert "chronicle-recall" in command


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_setup_json_round_trips_special_project_on_both_platforms(
    platform, monkeypatch, capsys
):
    project = 'project"with\\slashes'
    monkeypatch.setattr(setup_cli.sys, "platform", platform)

    setup_cli.main(["--project", project])
    mcp_config, hook_config = _printed_json_documents(capsys.readouterr().out)
    hook_command = hook_config["hooks"]["SessionStart"][0]["hooks"][0]["command"]

    assert mcp_config["mcpServers"]["chronicle"]["env"]["CHRONICLE_PROJECT"] == project
    if platform == "win32":
        encoded = hook_command.split("-EncodedCommand ", maxsplit=1)[1]
        script = base64.b64decode(encoded).decode("utf-16le")
        assert setup_cli._powershell_quote(project) in script
    else:
        assert project in hook_command


def test_windows_hook_and_codex_commands_encode_every_interpolated_value(
    monkeypatch, capsys
):
    # Uses the real local install path (whatever OS this test runs on) —
    # only the quoting/encoding logic is under test here, not real Windows
    # path resolution, which the windows-latest CI job exercises for real.
    project = "$`'\""
    monkeypatch.setattr(setup_cli.sys, "platform", "win32")

    setup_cli.main(["--project", project])
    out = capsys.readouterr().out
    mcp_config, hook_config = _printed_json_documents(out)
    install_path = mcp_config["mcpServers"]["chronicle"]["args"][1]
    hook_command = hook_config["hooks"]["SessionStart"][0]["hooks"][0]["command"]

    assert hook_command.startswith("powershell.exe -NoProfile -EncodedCommand ")
    encoded = hook_command.split("-EncodedCommand ", maxsplit=1)[1]
    script = base64.b64decode(encoded).decode("utf-16le")

    expected_script = (
        f"$env:CHRONICLE_PROJECT={setup_cli._powershell_quote(project)}; "
        f"uv run --directory {setup_cli._powershell_quote(install_path)} chronicle-recall"
    )
    expected_codex = (
        "codex mcp add chronicle -- "
        f"uv run --project {setup_cli._powershell_quote(install_path)} chronicle"
    )

    assert script == expected_script
    assert _codex_command(out) == expected_codex
