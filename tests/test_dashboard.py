from starlette.routing import Mount, Route

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
