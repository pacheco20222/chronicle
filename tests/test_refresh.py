import threading

import pytest

from chronicle import config, dashboard_cli, embeddings, refresh, semantic_cli, server


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.setattr(refresh, "_state", {"status": "idle", "done": 0, "total": 0, "error": None})
    monkeypatch.setattr(embeddings, "embed_text", lambda text: [float(len(text))])


def wait_until_finished():
    for thread in threading.enumerate():
        if thread.name == "chronicle-refresh":
            thread.join(timeout=5)


def test_reindex_reports_progress(service):
    for text in ("one", "two", "three"):
        service.add_memory([0.0], text, "p", "note")
    seen = []

    semantic_cli.reindex(service, lambda t: [0.0], say=lambda m: None, progress=lambda d, t: seen.append((d, t)))

    assert seen == [(0, 3), (1, 3), (2, 3), (3, 3)]


def test_refresh_all_reindexes_every_project_and_reports_done(service):
    service.add_memory([0.0], "a", "p1", "note")
    service.add_memory([0.0], "b", "p2", "note")
    service.vector_index.points.clear()

    server.memory_refresh_all()
    wait_until_finished()

    assert server.memory_refresh_status() == {"status": "done", "done": 2, "total": 2, "error": None}
    assert len(service.vector_index.points) == 2


def test_refresh_reports_a_failure_instead_of_crashing(service, monkeypatch):
    service.add_memory([0.0], "a", "p1", "note")

    def boom(text):
        raise ConnectionError("qdrant down")

    monkeypatch.setattr(embeddings, "embed_text", boom)
    server.memory_refresh_all()
    wait_until_finished()

    status = server.memory_refresh_status()
    assert status["status"] == "error"
    assert "qdrant down" in status["error"]


def test_second_start_while_running_does_not_spawn_another_job(service, monkeypatch):
    monkeypatch.setitem(refresh._state, "status", "running")
    started = []
    monkeypatch.setattr(refresh.threading, "Thread", lambda **kw: started.append(kw))

    assert refresh.start(service)["status"] == "running"
    assert started == []


def test_refresh_tool_refuses_in_keyword_only_mode(monkeypatch):
    monkeypatch.setenv("CHRONICLE_SEMANTIC", "0")

    with pytest.raises(server.ToolError, match="semantic search is off"):
        server.memory_refresh_all()


def test_dashboard_start_kicks_off_a_refresh(monkeypatch, service):
    calls = []
    monkeypatch.setattr(refresh, "start", lambda svc: calls.append(svc))
    monkeypatch.setattr(dashboard_cli.uvicorn, "run", lambda *a, **k: None)
    monkeypatch.setattr(dashboard_cli, "build_app", lambda: None)

    dashboard_cli.run_foreground(9)

    assert calls == [service]


def test_dashboard_start_survives_a_failed_refresh(monkeypatch, capsys):
    def boom(svc):
        raise RuntimeError("no qdrant")

    monkeypatch.setattr(refresh, "start", boom)
    monkeypatch.setattr(dashboard_cli.uvicorn, "run", lambda *a, **k: None)
    monkeypatch.setattr(dashboard_cli, "build_app", lambda: None)

    dashboard_cli.run_foreground(9)

    assert "skipped the startup refresh" in capsys.readouterr().err
