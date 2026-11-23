import base64
import json
import shlex
import subprocess
from pathlib import Path

import pytest

from chronicle import setup_cli
from chronicle.setup_global import setup_global


@pytest.fixture(autouse=True)
def isolated_apps(tmp_path, monkeypatch):
    clone = tmp_path / "clone's folder"
    (clone / "src" / "chronicle").mkdir(parents=True)
    (clone / "pyproject.toml").touch()
    for directory, suffix in [("bin", ""), ("Scripts", ".exe")]:
        scripts = clone / ".venv" / directory
        scripts.mkdir(parents=True)
        for name in ["chronicle", "chronicle-recall"]:
            (scripts / (name + suffix)).touch()
    monkeypatch.setattr(setup_cli, "__file__", str(clone / "src" / "chronicle" / "setup_cli.py"))
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(setup_cli.shutil, "which", lambda name: None)
    monkeypatch.setattr(setup_cli.subprocess, "run", lambda *a, **kw: pytest.fail("unexpected command"))
    monkeypatch.setattr(setup_cli, "_desktop_config_path", lambda: home / "Claude" / "config.json")
    return home


@pytest.fixture
def fake_home(isolated_apps, monkeypatch):
    (isolated_apps / ".cursor").mkdir()
    (isolated_apps / "Claude").mkdir()
    monkeypatch.setattr(setup_cli.shutil, "which", lambda name: {
        "claude": "/bin/claude", "codex": "/bin/codex", "uv": "/tools/uv",
    }.get(name))
    return isolated_apps


@pytest.fixture
def calls(monkeypatch):
    recorded = []

    def run(command, **kwargs):
        assert kwargs == {"check": False}
        recorded.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(setup_cli.subprocess, "run", run)
    return recorded


def test_entries_have_no_pinned_project(fake_home, calls):
    setup_global(dry_run=False, hook=True)
    install_dir = Path(setup_cli.__file__).resolve().parents[2]
    for path in [fake_home / ".cursor" / "mcp.json", fake_home / "Claude" / "config.json"]:
        entry = json.loads(path.read_text())["mcpServers"]["chronicle"]
        assert entry == {
            "command": (install_dir / ".venv" / ("Scripts/chronicle.exe" if setup_cli.sys.platform == "win32" else "bin/chronicle")).as_posix(),
            "args": [],
        }


def test_claude_code_uses_user_scope_and_user_hook(fake_home, calls):
    setup_global(dry_run=False, hook=True)
    clone = Path(setup_cli.__file__).resolve().parents[2]
    command = [(clone / ".venv" / ("Scripts/chronicle.exe" if setup_cli.sys.platform == "win32" else "bin/chronicle")).as_posix()]
    assert calls == [
        ["claude", "mcp", "add", "--scope", "user", "chronicle", "--", *command],
        ["codex", "mcp", "add", "chronicle", "--", *command],
    ]
    settings = json.loads((fake_home / ".claude" / "settings.json").read_text())
    group = settings["hooks"]["SessionStart"][0]
    assert group["matcher"] == "startup|resume|clear"
    hook = group["hooks"][0]["command"]
    if "-EncodedCommand " in hook:
        hook = base64.b64decode(hook.split("-EncodedCommand ")[1]).decode("utf-16le")
    assert "chronicle-recall" in hook and "CHRONICLE_PROJECT" not in hook
    assert "uv" not in hook
    assert not list(fake_home.rglob("projects.json"))
    assert not (Path.cwd() / "projects.json").exists()


def test_print_mode_changes_nothing(fake_home, calls):
    before = sorted(fake_home.rglob("*"))
    lines = setup_global(dry_run=True, hook=True)
    assert calls == [] and sorted(fake_home.rglob("*")) == before
    assert any("claude mcp add --scope user chronicle -- " in line and ".venv/" in line for line in lines)
    assert any("codex mcp add chronicle -- " in line and ".venv/" in line for line in lines)
    assert any("Would add this SessionStart hook" in line for line in lines)


def test_missing_apps_are_skipped(isolated_apps):
    assert setup_global(dry_run=True, hook=True) == [
        "skipped: Claude Code not found", "skipped: Cursor not found",
        "skipped: Codex not found", "skipped: Claude Desktop not found",
    ]
    assert list(isolated_apps.iterdir()) == []


def test_linux_skips_desktop_instead_of_exiting(isolated_apps, monkeypatch):
    def unsupported():
        raise SystemExit("Claude Desktop is only available on macOS and Windows.")

    monkeypatch.setattr(setup_cli, "_desktop_config_path", unsupported)
    assert setup_global(dry_run=False, hook=True)[-1] == "skipped: Claude Desktop not found"


def test_warns_about_a_project_level_chronicle_server(fake_home, calls):
    path = Path.cwd() / ".mcp.json"
    original = '{"mcpServers": {"chronicle": {}}}'
    path.write_text(original)
    lines = setup_global(dry_run=False, hook=True)
    assert "also defines 'chronicle'" in lines[-1]
    assert path.read_text() == original
    assert not path.with_suffix(".json.bak").exists()


@pytest.mark.parametrize("content", ['{"mcpServers": {"other": {}}}', '{bad', '[]', '{"mcpServers": []}'])
def test_unrelated_or_malformed_local_config_does_not_block_setup(isolated_apps, content):
    (Path.cwd() / ".mcp.json").write_text(content)
    assert len(setup_global(dry_run=True, hook=True)) == 4


@pytest.mark.parametrize("arguments", [["--project", "x"], ["--project", ""], ["cursor"]])
def test_global_rejects_project_flag_and_agent(arguments, capsys):
    with pytest.raises(SystemExit) as error:
        setup_cli.main(["--global", *arguments])
    assert error.value.code == 2
    assert "--global" in capsys.readouterr().err


def test_main_prints_global_lines_and_honors_flags(fake_home, calls, capsys):
    setup_cli.main(["--global", "--print", "--no-hook"])
    output = capsys.readouterr().out
    assert "claude mcp add --scope user chronicle" in output
    assert "codex mcp add chronicle" in output
    assert "SessionStart" not in output
    assert calls == []
    assert not (fake_home / ".claude").exists()
    assert not (fake_home / ".cursor" / "mcp.json").exists()


@pytest.mark.parametrize("failed_app", ["claude", "codex"])
def test_failed_cli_continues_with_other_apps(fake_home, calls, monkeypatch, failed_app):
    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, int(command[0] == failed_app))

    monkeypatch.setattr(setup_cli.subprocess, "run", run)
    lines = setup_global(dry_run=False, hook=False)
    assert any(failed_app in line and "failed" in line for line in lines)
    assert [command[0] for command in calls] == ["claude", "codex"]
    assert (fake_home / ".cursor" / "mcp.json").is_file()
    assert (fake_home / "Claude" / "config.json").is_file()
    assert "Fully quit Claude Desktop" in lines[-1]


def test_global_preserves_configs_and_replaces_pinned_hook(fake_home, calls):
    cursor = fake_home / ".cursor" / "mcp.json"
    original = {"preferences": {"x": 1}, "mcpServers": {"other": {"command": "foo"}}}
    cursor.write_text(json.dumps(original))
    settings = fake_home / ".claude" / "settings.json"
    setup_cli._merge_hook(settings, "CHRONICLE_PROJECT=old chronicle-recall", False)
    setup_global(dry_run=False, hook=True)
    setup_global(dry_run=False, hook=True)
    config = json.loads(cursor.read_text())
    assert config["preferences"] == original["preferences"]
    assert config["mcpServers"]["other"] == original["mcpServers"]["other"]
    assert json.loads(cursor.with_name("mcp.json.bak").read_text()) == original
    hooks = json.loads(settings.read_text())["hooks"]["SessionStart"]
    assert len(hooks) == 1 and len(hooks[0]["hooks"]) == 1


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_none_project_helpers_support_clone_and_wheel(isolated_apps, monkeypatch, platform):
    monkeypatch.setattr(setup_cli.sys, "platform", platform)
    clone = Path(setup_cli.__file__).resolve().parents[2]
    for install_dir in [clone, isolated_apps]:
        entry = setup_cli._server_entry(None, install_dir)
        assert "env" not in entry
        assert "--directory" not in entry["args"]
        if install_dir == clone:
            executable = clone / ".venv" / ("Scripts/chronicle.exe" if platform == "win32" else "bin/chronicle")
            assert entry == {"command": executable.as_posix(), "args": []}
            assert "uv" not in json.dumps(entry)
        command = setup_cli._recall_hook_command(None, install_dir)
        if platform == "win32":
            command = base64.b64decode(command.split("-EncodedCommand ")[1]).decode("utf-16le")
        assert "CHRONICLE_PROJECT" not in command
        assert "--directory" not in command
        if install_dir == clone:
            assert ".venv/" in command
            assert "uv" not in command
        assert "chronicle-recall" in command or "-m chronicle.recall" in command


def test_global_prefers_installed_executable(fake_home, calls, monkeypatch):
    executable = fake_home / "bin" / "chronicle"
    monkeypatch.setattr(setup_cli, "_chronicle_exe", lambda: executable.as_posix())
    setup_global(dry_run=False, hook=False)
    assert calls[0][-2:] == ["--", executable.as_posix()]
    assert json.loads((fake_home / ".cursor" / "mcp.json").read_text())["mcpServers"]["chronicle"] == {
        "command": executable.as_posix(), "args": [],
    }


@pytest.mark.parametrize("client", [".cursor/mcp.json", "Claude/config.json"])
@pytest.mark.parametrize("dry_run", [False, True])
def test_global_preserves_pinned_entry(fake_home, calls, capsys, client, dry_run):
    path = fake_home / client
    original = b'{ "mcpServers": { "chronicle": { "command": "old", "env": { "CHRONICLE_PROJECT": "dolphin" } } } }\n'
    path.write_bytes(original)

    setup_cli.main(["--global", "--no-hook", *(["--print"] if dry_run else [])])

    assert path.read_bytes() == original
    assert not path.with_name(path.name + ".bak").exists()
    output = capsys.readouterr().out
    assert "pinned to project 'dolphin'" in output
    assert "Remove env.CHRONICLE_PROJECT" in output
    assert str(path) in output


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_global_clone_hook_preserves_cwd(isolated_apps, monkeypatch, platform):
    monkeypatch.setattr(setup_cli.sys, "platform", platform)
    clone = Path(setup_cli.__file__).resolve().parents[2]

    command = setup_cli._recall_hook_command(None, clone)

    if platform == "win32":
        command = base64.b64decode(command.split("-EncodedCommand ")[1]).decode("utf-16le")
    executable = (clone / ".venv" / ("Scripts/chronicle-recall.exe" if platform == "win32" else "bin/chronicle-recall")).as_posix()
    expected = "& '" + executable.replace("'", "''") + "'" if platform == "win32" else shlex.quote(executable)
    assert command == expected
    assert "uv" not in command
    assert "--directory" not in command
    assert "CHRONICLE_PROJECT" not in command


@pytest.mark.parametrize("platform", ["linux", "win32"])
@pytest.mark.parametrize("name", ["chronicle", "chronicle-recall"])
def test_missing_clone_executable_aborts_before_any_write(fake_home, calls, monkeypatch, platform, name):
    monkeypatch.setattr(setup_cli.sys, "platform", platform)
    clone = Path(setup_cli.__file__).resolve().parents[2]
    directory, suffix = ("Scripts", ".exe") if platform == "win32" else ("bin", "")
    (clone / ".venv" / directory / (name + suffix)).unlink()
    before = sorted(fake_home.rglob("*"))

    with pytest.raises(SystemExit) as error:
        setup_cli.main(["--global"])

    message = str(error.value)
    assert "uv sync" in message and "in the clone" in message
    assert "uv tool install --editable ." in message
    assert "nothing was changed" in message
    assert sorted(fake_home.rglob("*")) == before
    assert calls == []


@pytest.mark.parametrize("helper,name", [
    (setup_cli._server_entry, "chronicle"),
    (setup_cli._recall_hook_command, "chronicle-recall"),
])
def test_global_helpers_reject_missing_clone_executable(isolated_apps, helper, name):
    clone = Path(setup_cli.__file__).resolve().parents[2]
    directory, suffix = ("Scripts", ".exe") if setup_cli.sys.platform == "win32" else ("bin", "")
    (clone / ".venv" / directory / (name + suffix)).unlink()
    with pytest.raises(SystemExit, match="uv sync"):
        helper(None, clone)
