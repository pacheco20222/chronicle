import json

import pytest

from chronicle import config, embeddings, semantic_cli, server
from chronicle.core import runtime
from chronicle.core.null_index import NullVectorIndex
from chronicle.core.repository import MemoryRepository
from chronicle.core.service import MemoryService
from chronicle.storage.database import Database


@pytest.fixture
def lexical_service(tmp_path, monkeypatch):
    monkeypatch.setenv("CHRONICLE_SEMANTIC", "0")
    database = Database(f"sqlite:///{tmp_path / 'lex.db'}")
    return MemoryService(MemoryRepository(database), NullVectorIndex())


def test_semantic_is_off_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("CHRONICLE_SEMANTIC", raising=False)
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
    assert config.semantic_enabled() is False


def test_config_file_and_env_override(tmp_path, monkeypatch):
    monkeypatch.delenv("CHRONICLE_SEMANTIC", raising=False)
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
    config.set_semantic(True)
    assert json.loads((tmp_path / "config.json").read_text()) == {"semantic": True}
    assert config.semantic_enabled() is True
    monkeypatch.setenv("CHRONICLE_SEMANTIC", "0")
    assert config.semantic_enabled() is False


def test_set_semantic_keeps_other_keys_and_survives_bad_file(tmp_path, monkeypatch):
    monkeypatch.delenv("CHRONICLE_SEMANTIC", raising=False)
    path = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", path)
    path.write_text(json.dumps({"other": 1}))
    config.set_semantic(True)
    assert json.loads(path.read_text()) == {"other": 1, "semantic": True}
    path.write_text("{ not json")
    assert config.semantic_enabled() is False


def test_runtime_uses_null_index_when_off(tmp_path, monkeypatch):
    monkeypatch.setenv("CHRONICLE_SEMANTIC", "0")
    service = runtime.create_runtime(database=Database(f"sqlite:///{tmp_path / 'r.db'}"))
    assert isinstance(service.vector_index, NullVectorIndex)


def test_embed_or_empty_never_touches_the_model_when_off(monkeypatch):
    monkeypatch.setenv("CHRONICLE_SEMANTIC", "0")
    monkeypatch.setattr(embeddings, "embed_text", lambda text: pytest.fail("model must not load"))
    assert embeddings.embed_or_empty("hello") == []


def test_save_and_keyword_search_work_without_vectors(lexical_service):
    memory_id = lexical_service.add_memory([], "We chose JWT for auth", "p", "decision")
    results = lexical_service.search([], "p", query_text="what did we choose for auth")
    assert [r["id"] for r in results] == [memory_id]
    assert lexical_service.get_latest("p", "decision")["id"] == memory_id


def test_lexical_search_is_still_project_scoped(lexical_service):
    lexical_service.add_memory([], "alpha secret", "other", "note")
    assert lexical_service.search([], "p", query_text="alpha secret") == []


def test_graph_data_lists_memories_without_vectors(lexical_service):
    lexical_service.add_memory([], "one", "p", "note")
    lexical_service.add_memory([], "two", "p", "note")
    records = lexical_service.get_all_with_vectors()
    assert len(records) == 2 and all(r["vector"] is None for r in records)
    from chronicle import graph_cli

    graph = graph_cli._build_graph_data(records, cross_project=False, current_project=None)
    assert len(graph["nodes"]) == 2 and graph["edges"] == []


def test_mcp_tools_work_in_lexical_mode(lexical_service, monkeypatch):
    monkeypatch.setattr(server, "_service", lexical_service)
    monkeypatch.setattr(embeddings, "embed_text", lambda text: pytest.fail("model must not load"))
    monkeypatch.setenv("CHRONICLE_PROJECT", "p")
    saved = server.memory_add("Deploy runs on every merge to main", "note")
    found = server.memory_search("how does deploy work")
    assert [r["id"] for r in found][:1] == [saved["id"]]


def test_reindex_embeds_every_live_memory(service):
    keep = service.add_memory([0.0], "keep me", "p", "note")
    gone = service.add_memory([0.0], "drop me", "p", "note")
    service.retract_memory(gone)
    service.vector_index.points.clear()
    count = semantic_cli.reindex(service, lambda text: [float(len(text))], say=lambda m: None)
    assert count == 1
    assert set(service.vector_index.points) == {keep}


def test_semantic_commands_toggle_the_setting(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("CHRONICLE_SEMANTIC", raising=False)
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
    semantic_cli.main(["status"])
    assert "off" in capsys.readouterr().out
    config.set_semantic(True)
    semantic_cli.main(["status"])
    assert "on" in capsys.readouterr().out
    semantic_cli.main(["disable"])
    assert config.semantic_enabled() is False


def test_semantic_enable_explains_missing_extra(monkeypatch):
    import importlib.util

    import sys

    monkeypatch.delitem(sys.modules, "fastembed", raising=False)
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a: None if name == "fastembed" else real(name, *a))
    with pytest.raises(SystemExit, match=r"\[semantic\]"):
        semantic_cli.main(["enable"])


def test_runtime_with_semantic_on_but_extra_missing_fails_clearly(tmp_path, monkeypatch):
    import importlib.util

    import sys

    monkeypatch.setenv("CHRONICLE_SEMANTIC", "1")
    monkeypatch.delitem(sys.modules, "qdrant_client", raising=False)
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a: None if name == "qdrant_client" else real(name, *a))
    with pytest.raises(RuntimeError, match="qdrant_client"):
        runtime.create_runtime(database=Database(f"sqlite:///{tmp_path / 'x.db'}"))
