import threading
from pathlib import Path

import pytest

from chronicle import config, dashboard_cli, embeddings, refresh, semantic_cli, server


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.setattr(refresh, "_state", dict(refresh._IDLE))
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

    assert server.memory_refresh_status() == {
        "status": "done",
        "label": "Re-embedding memories",
        "done": 2,
        "total": 2,
        "error": None,
    }
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


def test_background_start_prints_the_dashboard_link(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("CHRONICLE_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(dashboard_cli.subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 42})())

    dashboard_cli.start_background(8765)

    assert "http://127.0.0.1:8765" in capsys.readouterr().out


@pytest.fixture
def docs_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("CHRONICLE_REGISTRY_PATH", str(tmp_path / "projects.json"))
    folder = tmp_path / "myproj"
    (folder / "docs").mkdir(parents=True)
    (folder / "README.md").write_text("# Hello\n\nabout the project", encoding="utf-8")
    (folder / "docs" / "design.txt").write_text("design notes", encoding="utf-8")
    (folder / "node_modules" / "dep").mkdir(parents=True)
    (folder / "node_modules" / "dep" / "README.md").write_text("third party", encoding="utf-8")
    return folder


def test_add_project_registers_the_folder_and_imports_its_documents(service, docs_folder):
    result = server.memory_add_project(str(docs_folder), "myproj")
    wait_until_finished()

    assert result["status"] == "running"
    assert refresh.status()["status"] == "done"
    assert (refresh.status()["done"], refresh.status()["total"]) == (2, 2)  # node_modules skipped
    assert server.registry.list_projects() == {"myproj": [str(docs_folder.resolve())]}
    assert {m["content"] for m in service.get_all_with_vectors("myproj")} == {
        "# Hello\n\nabout the project",
        "design notes",
    }


def test_adding_a_folder_again_only_imports_what_changed(service, docs_folder):
    server.memory_add_project(str(docs_folder), "myproj")
    wait_until_finished()
    (docs_folder / "README.md").write_text("rewritten", encoding="utf-8")

    server.memory_add_project(str(docs_folder), "myproj")
    wait_until_finished()

    live = {m["content"] for m in service.get_all_with_vectors("myproj") if m["status"] == "active"}
    assert live == {"rewritten", "design notes"}


def test_add_project_rejects_bad_input_before_starting_a_job(service, docs_folder, tmp_path):
    with pytest.raises(server.ToolError, match="not a folder"):
        server.memory_add_project(str(tmp_path / "missing"), "x")
    with pytest.raises(server.ToolError, match="name is required"):
        server.memory_add_project(str(docs_folder), "  ")
    with pytest.raises(server.ToolError):
        server.memory_add_project(str(docs_folder), "x", type="bogus")
    with pytest.raises(server.ToolError, match="home/root"):
        server.memory_add_project(str(Path.home()), "x")
    assert refresh.status()["status"] == "idle"


def test_list_folders_shows_visible_subfolders_and_the_parent(tmp_path):
    (tmp_path / "b").mkdir()
    (tmp_path / "A").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "file.txt").write_text("x")

    listing = server.memory_list_folders(str(tmp_path))

    assert listing == {"path": str(tmp_path.resolve()), "parent": str(tmp_path.resolve().parent), "folders": ["A", "b"]}
    with pytest.raises(server.ToolError):
        server.memory_list_folders(str(tmp_path / "file.txt"))


def test_add_project_while_a_job_runs_refuses_instead_of_dropping_the_import(service, docs_folder, monkeypatch):
    monkeypatch.setitem(refresh._state, "status", "running")

    with pytest.raises(server.ToolError, match="already running"):
        server.memory_add_project(str(docs_folder), "myproj")

    assert server.registry.list_projects() == {}
