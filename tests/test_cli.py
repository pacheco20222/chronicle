import subprocess

import pytest

from chronicle import cli, dashboard_cli, services


def _run(monkeypatch, *args):
    monkeypatch.setattr(cli.sys, "argv", ["chronicle", *args])
    cli.main()


@pytest.fixture
def served(monkeypatch):
    calls = []
    fake = lambda argv: calls.append(argv)  # noqa: E731
    monkeypatch.setattr(cli, "_serve", fake)
    monkeypatch.setitem(cli.COMMANDS, "serve", fake)
    return calls


def test_bare_chronicle_in_a_terminal_prints_help(monkeypatch, capsys, served):
    monkeypatch.setattr(cli, "_stdin_is_terminal", lambda: True)
    monkeypatch.setattr(services, "status_lines", lambda: ["Status: ready"])

    _run(monkeypatch)

    out = capsys.readouterr().out
    assert "usage: chronicle <command>" in out
    assert served == []


def test_bare_chronicle_from_an_mcp_client_starts_the_server(monkeypatch, capsys, served):
    monkeypatch.setattr(cli, "_stdin_is_terminal", lambda: False)

    _run(monkeypatch)

    assert served == [[]]
    captured = capsys.readouterr()
    # stdout is the MCP stdio channel: nothing may be printed there.
    assert captured.out == ""
    assert "chronicle --help" in captured.err


def test_serve_starts_the_server(monkeypatch, served):
    monkeypatch.setattr(cli, "_stdin_is_terminal", lambda: True)

    _run(monkeypatch, "serve")

    assert served == [[]]


@pytest.mark.parametrize("flag", ["-h", "--help", "help"])
def test_help_flags_print_help_without_serving(monkeypatch, capsys, served, flag):
    _run(monkeypatch, flag)

    assert "usage: chronicle <command>" in capsys.readouterr().out
    assert served == []


def test_help_lists_every_command():
    for command in cli.COMMANDS:
        assert f"  {command}" in cli.HELP


def test_version_flag(monkeypatch, capsys):
    _run(monkeypatch, "--version")

    assert capsys.readouterr().out.startswith("chronicle ")


def test_unknown_command_errors_instead_of_starting_the_server(monkeypatch, capsys, served):
    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, "dashbord")

    assert exc.value.code == 2
    assert "unknown command 'dashbord'" in capsys.readouterr().err
    assert served == []


def test_start_ensures_qdrant_then_starts_dashboard(monkeypatch):
    order = []
    monkeypatch.setattr(services, "ensure_qdrant", lambda: order.append("qdrant"))
    monkeypatch.setattr(dashboard_cli, "main", lambda argv: order.append(argv))

    _run(monkeypatch, "start", "--port", "9000", "--background")

    assert order == ["qdrant", ["start", "--port", "9000", "--background"]]


def test_stop_stops_the_dashboard(monkeypatch):
    seen = []
    monkeypatch.setattr(dashboard_cli, "main", lambda argv: seen.append(argv))

    _run(monkeypatch, "stop")

    assert seen == [["stop"]]


def test_ensure_qdrant_does_nothing_when_already_running(monkeypatch):
    monkeypatch.setattr(services, "qdrant_is_reachable", lambda url=None, timeout=2: True)
    monkeypatch.setattr(services.subprocess, "run", lambda *a, **k: pytest.fail("docker must not run"))

    services.ensure_qdrant()


def test_ensure_qdrant_starts_bundled_compose_when_down(monkeypatch):
    reachable = iter([False, False, True])
    calls = []
    monkeypatch.setattr(services, "qdrant_is_reachable", lambda url=None, timeout=2: next(reachable))
    monkeypatch.setattr(services, "docker_state", lambda: services.DOCKER_RUNNING)
    monkeypatch.setattr(services.time, "sleep", lambda seconds: None)

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(services.subprocess, "run", fake_run)

    services.ensure_qdrant()

    assert calls == [["docker", "compose", "-f", str(services.compose_file()), "up", "-d"]]


@pytest.mark.parametrize(
    "state, expected",
    [
        (services.DOCKER_NOT_INSTALLED, "Docker is not installed"),
        (services.DOCKER_NOT_RUNNING, "Open Docker Desktop"),
    ],
)
def test_ensure_qdrant_tells_you_to_install_or_open_docker(monkeypatch, state, expected):
    monkeypatch.setattr(services, "qdrant_is_reachable", lambda url=None, timeout=2: False)
    monkeypatch.setattr(services, "docker_state", lambda: state)
    monkeypatch.setattr(services.subprocess, "run", lambda *a, **k: pytest.fail("compose must not run"))

    with pytest.raises(SystemExit, match=expected):
        services.ensure_qdrant()


def test_docker_state_not_installed_when_cli_missing(monkeypatch):
    monkeypatch.setattr(services.shutil, "which", lambda name: None)

    assert services.docker_state() == services.DOCKER_NOT_INSTALLED


@pytest.mark.parametrize(
    "returncode, expected",
    [(0, services.DOCKER_RUNNING), (1, services.DOCKER_NOT_RUNNING)],
)
def test_docker_state_asks_the_daemon(monkeypatch, returncode, expected):
    monkeypatch.setattr(services.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(
        services.subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(args, returncode, stdout="", stderr=""),
    )

    assert services.docker_state() == expected


def test_docker_state_treats_a_hung_daemon_as_not_running(monkeypatch):
    monkeypatch.setattr(services.shutil, "which", lambda name: "/usr/bin/docker")

    def hang(args, **kwargs):
        raise subprocess.TimeoutExpired(args, 15)

    monkeypatch.setattr(services.subprocess, "run", hang)

    assert services.docker_state() == services.DOCKER_NOT_RUNNING


@pytest.mark.parametrize(
    "state, expected",
    [
        (services.DOCKER_NOT_INSTALLED, "Docker is not installed"),
        (services.DOCKER_NOT_RUNNING, "Open Docker Desktop"),
        (services.DOCKER_RUNNING, "chronicle start"),
    ],
)
def test_qdrant_down_message_points_at_the_actual_fix(monkeypatch, state, expected):
    monkeypatch.setattr(services, "docker_state", lambda: state)

    message = services.qdrant_down_message()

    assert "can't reach Qdrant" in message
    assert expected in message


def test_bare_chronicle_in_a_terminal_reports_docker_status(monkeypatch, capsys, served):
    monkeypatch.setattr(cli, "_stdin_is_terminal", lambda: True)
    monkeypatch.setattr(services, "qdrant_is_reachable", lambda url=None, timeout=2: False)
    monkeypatch.setattr(services, "docker_state", lambda: services.DOCKER_NOT_RUNNING)

    _run(monkeypatch)

    out = capsys.readouterr().out
    assert "usage: chronicle <command>" in out
    assert "Status: not ready" in out
    assert "Open Docker Desktop" in out


def test_ensure_qdrant_does_not_start_docker_for_a_remote_url(monkeypatch):
    monkeypatch.setattr(services.config, "QDRANT_URL", "http://qdrant.example.com:6333")
    monkeypatch.setattr(services, "qdrant_is_reachable", lambda url=None, timeout=2: False)
    monkeypatch.setattr(services.subprocess, "run", lambda *a, **k: pytest.fail("docker must not run"))

    with pytest.raises(SystemExit, match="isn't local"):
        services.ensure_qdrant()
