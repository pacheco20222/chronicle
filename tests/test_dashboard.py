import json
import os
import subprocess
import sys

import pytest
from starlette.routing import Mount, Route
from starlette.testclient import TestClient

from chronicle import cli, dashboard, dashboard_cli, server


def test_dashboard_app_exposes_streamable_http_on_mcp_path():
    app = dashboard_cli.build_app()

    routes = [route for route in app.routes if isinstance(route, (Route, Mount))]

    assert any(route.path == "/mcp" and "POST" in route.methods for route in routes)


def test_dashboard_start_defaults_to_localhost_and_configurable_port(monkeypatch):
    calls = {}

    def fake_run(app, **kwargs):
        calls["app"] = app
        calls.update(kwargs)

    monkeypatch.setattr(dashboard_cli.uvicorn, "run", fake_run)

    dashboard_cli.run_foreground(9911)

    assert calls["host"] == "127.0.0.1"
    assert calls["port"] == 9911
    assert calls["lifespan"] == "on"


def test_dashboard_graph_tool_reuses_existing_graph_builder(monkeypatch, service):
    records = [{"id": "a", "project": "p", "type": "note", "content": "x", "vector": [1.0]}]
    expected = {"nodes": [], "edges": []}
    seen = {}

    monkeypatch.setattr(service, "get_all_with_vectors", lambda project=None: records)
    monkeypatch.setattr(server, "_get_service", lambda: service)

    def fake_build(records_arg, **kwargs):
        seen["records"] = records_arg
        seen["kwargs"] = kwargs
        return expected

    monkeypatch.setattr(server.graph_cli, "_build_graph_data", fake_build)

    assert server.memory_dashboard_graph() == expected
    assert seen["records"] is records
    assert seen["kwargs"]["cross_project"] is False


def test_build_snapshot_includes_scopes_for_frontend(service):
    v = [0.1] * 768
    service.set_document(v, "azure core", "work/azure", "work/azure", "overview")
    service.add_memory(v, "note", "chronicle-test", "note")

    snapshot = dashboard.build_snapshot(service)

    assert "scopes" in snapshot["graph"]
    paths = {s["path"] for s in snapshot["graph"]["scopes"]}
    assert {"work", "work/azure", "chronicle-test"} <= paths


def test_cli_dispatches_dashboard_subcommand(monkeypatch):
    called = {}

    monkeypatch.setattr(cli.sys, "argv", ["chronicle", "dashboard", "stop"])
    monkeypatch.setattr(
        dashboard_cli,
        "main",
        lambda argv: called.setdefault("argv", argv),
    )

    cli.main()

    assert called["argv"] == ["stop"]


def test_dashboard_without_built_frontend_explains_how_to_build(monkeypatch, tmp_path):
    monkeypatch.setattr(dashboard_cli, "_dashboard_dist", lambda: tmp_path / "dashboard" / "dist")

    response = TestClient(dashboard_cli.build_app()).get("/")

    assert response.status_code == 503
    assert "npm run build" in response.text
    assert "not built" in response.text


def test_dashboard_serves_built_frontend(monkeypatch, tmp_path):
    (tmp_path / "index.html").write_text("<title>Chronicle / memory field</title>")
    monkeypatch.setattr(dashboard_cli, "_dashboard_dist", lambda: tmp_path)

    response = TestClient(dashboard_cli.build_app()).get("/")

    assert response.status_code == 200
    assert "memory field" in response.text


def test_dashboard_start_warns_when_frontend_not_built(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(dashboard_cli, "_dashboard_dist", lambda: tmp_path / "dist")
    monkeypatch.setattr(dashboard_cli.uvicorn, "run", lambda app, **kwargs: None)

    dashboard_cli.run_foreground(9911)

    assert "npm run build" in capsys.readouterr().err


@pytest.mark.parametrize(
    "command",
    [
        "uv run chronicle",
        "/opt/homebrew/bin/uv run chronicle dashboard start",
        "uv --project /path/to/chronicle run chronicle",
        "uv --directory C:/x/chronicle run chronicle",
        "uv run --project /path/to/chronicle chronicle",
        r'"C:\Users\me\.local\bin\uv.exe" run chronicle-recall',
    ],
)
def test_is_uv_run_chronicle_matches_chronicle_servers(command):
    assert dashboard._is_uv_run_chronicle(command)


@pytest.mark.parametrize(
    "command",
    [
        "uv run python -c \"from chronicle import dashboard\"",
        "uv run pytest tests/test_chronicle.py",
        "python -m chronicle",
        "uv sync",
        "",
    ],
)
def test_is_uv_run_chronicle_ignores_other_commands(command):
    assert not dashboard._is_uv_run_chronicle(command)


def _fake_powershell(stdout):
    def fake_run(args, **kwargs):
        assert args[0] == "powershell.exe"
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")

    return fake_run


def test_chronicle_processes_on_windows_uses_powershell(monkeypatch):
    rows = [
        {"pid": 10, "cpu": 3, "rss_kb": 2048, "command": "uv --project C:/c run chronicle"},
        {"pid": 11, "cpu": 0, "rss_kb": 1024, "command": "uv run python -c x"},
    ]
    monkeypatch.setattr(dashboard.sys, "platform", "win32")
    monkeypatch.setattr(dashboard.subprocess, "run", _fake_powershell(json.dumps(rows)))

    assert dashboard._chronicle_processes() == [
        {"pid": 10, "cpu_percent": "3", "rss_kb": 2048, "command": "uv --project C:/c run chronicle"}
    ]


@pytest.mark.parametrize(
    "stdout, expected_pids",
    [
        # ConvertTo-Json emits a bare object, not a list, for a single row.
        (json.dumps({"pid": 7, "cpu": None, "rss_kb": 1, "command": "uv run chronicle"}), [7]),
        ("", []),
        ("not json", []),
    ],
)
def test_chronicle_processes_on_windows_handles_powershell_output_shapes(monkeypatch, stdout, expected_pids):
    monkeypatch.setattr(dashboard.sys, "platform", "win32")
    monkeypatch.setattr(dashboard.subprocess, "run", _fake_powershell(stdout))

    assert [p["pid"] for p in dashboard._chronicle_processes()] == expected_pids


def test_stop_on_windows_kills_process_tree_without_signal_zero(monkeypatch, tmp_path):
    pid_file = tmp_path / "dashboard.pid"
    pid_file.write_text("4242")
    running = {"alive": True}
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        running["alive"] = False
        return subprocess.CompletedProcess(args, 0)

    def no_kill(*args):
        raise AssertionError("os.kill must not be used on Windows")

    monkeypatch.setattr(dashboard_cli.sys, "platform", "win32")
    monkeypatch.setattr(dashboard_cli, "pid_path", lambda: pid_file)
    monkeypatch.setattr(dashboard_cli, "_windows_pid_is_running", lambda pid: running["alive"])
    monkeypatch.setattr(dashboard_cli.os, "kill", no_kill)
    monkeypatch.setattr(dashboard_cli.subprocess, "run", fake_run)

    dashboard_cli.stop()

    assert calls == [["taskkill", "/PID", "4242", "/T", "/F"]]
    assert not pid_file.exists()


def test_background_start_detaches_per_platform(monkeypatch):
    monkeypatch.setattr(dashboard_cli.sys, "platform", "linux")
    assert dashboard_cli._background_popen_kwargs() == {"start_new_session": True}

    if sys.platform == "win32":
        monkeypatch.setattr(dashboard_cli.sys, "platform", "win32")
        flags = dashboard_cli._background_popen_kwargs()["creationflags"]
        assert flags & subprocess.CREATE_NO_WINDOW
        assert flags & subprocess.CREATE_NEW_PROCESS_GROUP


@pytest.mark.skipif(sys.platform != "win32", reason="Windows process API")
def test_windows_pid_is_running_against_real_processes():
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()

    assert dashboard_cli._pid_is_running(os.getpid())
    assert not dashboard_cli._pid_is_running(child.pid)
