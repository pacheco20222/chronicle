import json
import math
import pytest
from types import SimpleNamespace

from chronicle import graph_cli


def test_cosine_identical_vectors_is_one():
    v = [1.0, 2.0, 3.0]
    assert math.isclose(graph_cli._cosine(v, v), 1.0, rel_tol=1e-9)


def test_cosine_orthogonal_vectors_is_zero():
    assert math.isclose(graph_cli._cosine([1.0, 0.0], [0.0, 1.0]), 0.0, abs_tol=1e-9)


def test_build_graph_data_creates_knn_edges():
    records = [
        {"id": "a", "vector": [1.0, 0.0, 0.0], "project": "p", "type": "note", "content": "a"},
        {"id": "b", "vector": [0.99, 0.01, 0.0], "project": "p", "type": "note", "content": "b"},
        {"id": "c", "vector": [0.0, 1.0, 0.0], "project": "p", "type": "note", "content": "c"},
    ]
    graph = graph_cli._build_graph_data(records, k=1)
    assert graph["k"] == 1
    assert len(graph["nodes"]) == 3
    edge_pairs = {frozenset((e["source"], e["target"])) for e in graph["edges"]}
    assert frozenset(("a", "b")) in edge_pairs


def test_build_graph_data_nodes_carry_status_defaulting_to_active():
    records = [
        {"id": "a", "vector": [1.0, 0.0, 0.0], "project": "p", "type": "note", "content": "a", "status": "resolved"},
        {"id": "b", "vector": [0.99, 0.01, 0.0], "project": "p", "type": "note", "content": "b"},
    ]
    nodes = {n["id"]: n for n in graph_cli._build_graph_data(records, k=1)["nodes"]}
    assert nodes["a"]["status"] == "resolved"
    assert nodes["b"]["status"] == "active"


def test_build_graph_data_nodes_carry_provenance_and_temporal_fields():
    records = [
        {
            "id": "a",
            "vector": [1.0, 0.0],
            "project": "p",
            "type": "note",
            "content": "a",
            "source_id": "source-a",
            "source": "notes.md#L4",
            "episode_id": "episode-a",
            "episode_title": "Research session",
            "confidence": 0.8,
            "extraction_method": "manual",
            "valid_at": "2026-09-01T00:00:00+00:00",
            "invalid_at": None,
            "supersedes": "old-a",
            "relations": [{"type": "related_to", "target": "b"}],
        },
        {"id": "b", "vector": [0.0, 1.0], "project": "p", "type": "note", "content": "b"},
    ]

    node = next(node for node in graph_cli._build_graph_data(records, min_similarity=1.0)["nodes"] if node["id"] == "a")

    assert node == {
        "id": "a",
        "project": "p",
        "type": "note",
        "content": "a",
        "slug": None,
        "created_at": None,
        "status": "active",
        "role": "",
        "source_id": "source-a",
        "source": "notes.md#L4",
        "episode_id": "episode-a",
        "episode_title": "Research session",
        "confidence": 0.8,
        "extraction_method": "manual",
        "valid_at": "2026-09-01T00:00:00+00:00",
        "invalid_at": None,
        "supersedes": "old-a",
        "relations": [{"type": "related_to", "target": "b"}],
    }


def test_build_graph_data_carries_current_project():
    records = [
        {"id": "a", "vector": [1.0, 0.0, 0.0], "project": "p", "type": "note", "content": "a"},
        {"id": "b", "vector": [0.99, 0.01, 0.0], "project": "p", "type": "note", "content": "b"},
    ]
    graph = graph_cli._build_graph_data(records, k=1, current_project="p")
    assert graph["current_project"] == "p"


def test_build_graph_data_handles_k_larger_than_available_neighbors():
    records = [
        {"id": "a", "vector": [1.0, 0.0], "project": "p", "type": "note", "content": "a"},
        {"id": "b", "vector": [0.0, 1.0], "project": "p", "type": "note", "content": "b"},
    ]
    graph = graph_cli._build_graph_data(records, k=5, min_similarity=0.0)
    assert len(graph["edges"]) == 1


def test_build_graph_data_defaults_to_project_isolated_edges():
    records = [
        {"id": "a", "vector": [1.0, 0.0, 0.0], "project": "p", "type": "note", "content": "a"},
        {"id": "b", "vector": [1.0, 0.0, 0.0], "project": "q", "type": "note", "content": "b"},
    ]
    graph = graph_cli._build_graph_data(records, k=5, min_similarity=0.0)
    assert graph["edges"] == []


def test_build_graph_data_cross_project_allows_edges_across_projects():
    records = [
        {"id": "a", "vector": [1.0, 0.0, 0.0], "project": "p", "type": "note", "content": "a"},
        {"id": "b", "vector": [1.0, 0.0, 0.0], "project": "q", "type": "note", "content": "b"},
    ]
    graph = graph_cli._build_graph_data(records, k=5, cross_project=True, min_similarity=0.0)
    edge_pairs = {frozenset((e["source"], e["target"])) for e in graph["edges"]}
    assert frozenset(("a", "b")) in edge_pairs


def test_build_graph_data_includes_explicit_relation_edges():
    records = [
        {"id": "a", "vector": [1.0, 0.0], "project": "p", "type": "note", "content": "a",
         "relations": [{"type": "blocked_by", "target": "b"}]},
        {"id": "b", "vector": [0.0, 1.0], "project": "p", "type": "note", "content": "b"},
    ]
    graph = graph_cli._build_graph_data(records, k=5, min_similarity=1.0)
    explicit = [e for e in graph["edges"] if e["kind"] == "explicit"]
    assert len(explicit) == 1
    assert explicit[0]["source"] == "a"
    assert explicit[0]["target"] == "b"
    assert explicit[0]["relation"] == "blocked_by"


def test_build_graph_data_falls_back_to_bare_supersedes_field():
    records = [
        {"id": "a", "vector": [1.0, 0.0], "project": "p", "type": "note", "content": "a", "supersedes": "b"},
        {"id": "b", "vector": [0.0, 1.0], "project": "p", "type": "note", "content": "b"},
    ]
    graph = graph_cli._build_graph_data(records, k=5, min_similarity=1.0)
    explicit = [e for e in graph["edges"] if e["kind"] == "explicit"]
    assert len(explicit) == 1
    assert explicit[0]["relation"] == "supersedes"


def test_build_graph_data_ignores_relation_target_outside_record_set():
    records = [
        {"id": "a", "vector": [1.0, 0.0], "project": "p", "type": "note", "content": "a",
         "relations": [{"type": "related_to", "target": "missing"}]},
        {"id": "b", "vector": [0.0, 1.0], "project": "p", "type": "note", "content": "b"},
    ]
    graph = graph_cli._build_graph_data(records, k=5, min_similarity=1.0)
    assert [e for e in graph["edges"] if e["kind"] == "explicit"] == []


def test_build_graph_data_min_similarity_drops_weak_edges():
    records = [
        {"id": "a", "vector": [1.0, 0.0], "project": "p", "type": "note", "content": "a"},
        {"id": "b", "vector": [0.0, 1.0], "project": "p", "type": "note", "content": "b"},
    ]
    graph = graph_cli._build_graph_data(records, k=5, min_similarity=0.5)
    assert graph["edges"] == []


def test_render_html_embeds_graph_json():
    graph = {"nodes": [{"id": "a", "project": "p", "type": "note", "content": "hello"}], "edges": [], "k": 3}
    html = graph_cli._render_html(graph)
    assert "<title>Chronicle Graph</title>" in html
    assert json.dumps(graph, ensure_ascii=False) in html


def test_main_writes_html_file_and_opens_browser(tmp_path, monkeypatch, service):
    service.add_memory([1.0, 0.0], "graph cli test alpha", "chronicle-test", "note")
    service.add_memory([0.9, 0.1], "graph cli test beta", "chronicle-test", "note")

    opened = []
    monkeypatch.setattr(graph_cli.webbrowser, "open", lambda uri: opened.append(uri))
    monkeypatch.setattr(graph_cli, "get_runtime", lambda: service)

    out_path = tmp_path / "graph.html"
    graph_cli.main(["--project", "chronicle-test", "--out", str(out_path)])

    assert out_path.exists()
    content = out_path.read_text()
    assert "graph cli test alpha" in content
    assert len(opened) == 1


def test_main_handles_fewer_than_two_records(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(graph_cli.webbrowser, "open", lambda uri: (_ for _ in ()).throw(AssertionError("should not open browser")))
    out_path = tmp_path / "graph.html"
    graph_cli.main(["--project", "a-project-with-zero-memories-for-graph-test", "--out", str(out_path)])
    assert not out_path.exists()
    assert "at least 2" in capsys.readouterr().out


def test_main_without_project_or_all_uses_current_project(monkeypatch):
    monkeypatch.setenv("CHRONICLE_PROJECT", "env-project")
    seen = {}

    def fake_get_all_with_vectors(project=None):
        seen["project"] = project
        return []

    runtime = SimpleNamespace(get_all_with_vectors=fake_get_all_with_vectors)
    monkeypatch.setattr(graph_cli, "get_runtime", lambda: runtime)
    graph_cli.main([])
    assert seen["project"] == "env-project"


def test_main_with_all_flag_ignores_current_project(monkeypatch):
    monkeypatch.setenv("CHRONICLE_PROJECT", "env-project")
    seen = {}

    def fake_get_all_with_vectors(project=None):
        seen["project"] = project
        return []

    runtime = SimpleNamespace(get_all_with_vectors=fake_get_all_with_vectors)
    monkeypatch.setattr(graph_cli, "get_runtime", lambda: runtime)
    graph_cli.main(["--all"])
    assert seen["project"] is None


def test_main_rejects_project_and_all_together(monkeypatch):
    monkeypatch.setenv("CHRONICLE_PROJECT", "env-project")
    with pytest.raises(SystemExit):
        graph_cli.main(["--project", "x", "--all"])


def test_build_graph_data_marks_core_and_latest_checkpoint_per_project():
    def rec(i, project, type_, created, slug=None):
        return {"id": i, "vector": [1.0, float(len(i))], "project": project, "type": type_,
                "content": i, "slug": slug, "created_at": created}
    records = [
        rec("c1", "p", "checkpoint", "2026-09-01T00:00:00+00:00"),
        rec("c2", "p", "checkpoint", "2026-09-20T00:00:00+00:00"),
        rec("doc", "p", "overview", "2026-08-01T00:00:00+00:00", slug="p"),
        rec("old-doc", "q", "architecture", "2026-08-01T00:00:00+00:00", slug="q"),
        rec("q1", "q", "checkpoint", "2026-09-05T00:00:00+00:00"),
    ]
    roles = {n["id"]: n["role"] for n in graph_cli._build_graph_data(records, k=1)["nodes"]}
    assert roles == {"c1": "", "c2": "latest", "doc": "core", "old-doc": "core", "q1": "latest"}
