import json
import math
import os

import pytest

from mnemo import embeddings, graph_cli, store


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
    assert "<title>Mnemo Graph</title>" in html
    assert json.dumps(graph, ensure_ascii=False) in html


def test_main_writes_html_file_and_opens_browser(tmp_path, monkeypatch):
    client = store.get_client()
    collection = os.environ["MNEMO_COLLECTION"]
    store.ensure_collection(client, collection)
    store.add_memory(client, embeddings.embed_text("graph cli test alpha"), "graph cli test alpha", "mnemo-test", "note", collection=collection)
    store.add_memory(client, embeddings.embed_text("graph cli test beta"), "graph cli test beta", "mnemo-test", "note", collection=collection)

    opened = []
    monkeypatch.setattr(graph_cli.webbrowser, "open", lambda uri: opened.append(uri))
    monkeypatch.setattr(graph_cli.config, "COLLECTION_NAME", collection)

    out_path = tmp_path / "graph.html"
    graph_cli.main(["--project", "mnemo-test", "--out", str(out_path)])

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
    monkeypatch.setenv("MNEMO_PROJECT", "env-project")
    seen = {}

    def fake_get_all_with_vectors(client, project=None):
        seen["project"] = project
        return []

    monkeypatch.setattr(graph_cli.store, "get_all_with_vectors", fake_get_all_with_vectors)
    graph_cli.main([])
    assert seen["project"] == "env-project"


def test_main_with_all_flag_ignores_current_project(monkeypatch):
    monkeypatch.setenv("MNEMO_PROJECT", "env-project")
    seen = {}

    def fake_get_all_with_vectors(client, project=None):
        seen["project"] = project
        return []

    monkeypatch.setattr(graph_cli.store, "get_all_with_vectors", fake_get_all_with_vectors)
    graph_cli.main(["--all"])
    assert seen["project"] is None


def test_main_rejects_project_and_all_together(monkeypatch):
    monkeypatch.setenv("MNEMO_PROJECT", "env-project")
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
