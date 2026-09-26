from pathlib import Path

from chronicle import recall, registry


def test_latest_checkpoint_returns_none_when_nothing_saved():
    result = recall.latest_checkpoint("a-project-with-no-checkpoints-ever")
    assert result is None


def test_latest_checkpoint_formats_found_result(service):
    service.add_memory(
        [0.1] * 768, "investigated the auth bug, next step is X", "chronicle-test", "checkpoint"
    )

    result = recall.latest_checkpoint("chronicle-test")
    assert result is not None
    assert "investigated the auth bug, next step is X" in result


def test_latest_checkpoint_fails_open_on_connection_error(monkeypatch):
    monkeypatch.setattr(recall, "get_runtime", lambda: (_ for _ in ()).throw(OSError("offline")))
    result = recall.latest_checkpoint("chronicle-test")
    assert result is None


def test_overview_document_returns_none_when_nothing_saved():
    result = recall.overview_document("a-project-with-no-overview-ever")
    assert result is None


def test_overview_document_formats_found_result(service):
    service.set_document([0.2] * 768, "this project does X", "chronicle-test", "chronicle-test", "architecture")

    result = recall.overview_document("chronicle-test")
    assert result is not None
    assert "this project does X" in result


def test_overview_document_fails_open_on_connection_error(monkeypatch):
    monkeypatch.setattr(recall, "get_runtime", lambda: (_ for _ in ()).throw(OSError("offline")))
    result = recall.overview_document("chronicle-test")
    assert result is None


def test_main_falls_back_to_registry(monkeypatch, tmp_path, capsys, service):
    monkeypatch.delenv("CHRONICLE_PROJECT", raising=False)
    monkeypatch.setenv("CHRONICLE_REGISTRY_PATH", str(tmp_path / "projects.json"))
    registry.register(Path.cwd(), "chronicle-test")
    service.add_memory([0.1] * 768, "registry fallback checkpoint content", "chronicle-test", "checkpoint")

    recall.main()

    out = capsys.readouterr().out
    assert "registry fallback checkpoint content" in out


def test_main_does_nothing_when_neither_env_nor_registry(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("CHRONICLE_PROJECT", raising=False)
    monkeypatch.setenv("CHRONICLE_REGISTRY_PATH", str(tmp_path / "projects.json"))

    recall.main()

    out = capsys.readouterr().out
    assert out == ""


def test_main_never_constructs_runtime_when_unresolved(monkeypatch, tmp_path):
    monkeypatch.delenv("CHRONICLE_PROJECT", raising=False)
    monkeypatch.setenv("CHRONICLE_REGISTRY_PATH", str(tmp_path / "projects.json"))

    def _boom(*args, **kwargs):
        raise AssertionError("get_runtime() should not be called when project is unresolved")

    monkeypatch.setattr(recall, "get_runtime", _boom)

    recall.main()  # must not raise


def test_main_fails_open_on_corrupt_registry(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("CHRONICLE_PROJECT", raising=False)
    registry_path = tmp_path / "projects.json"
    monkeypatch.setenv("CHRONICLE_REGISTRY_PATH", str(registry_path))
    # Write corrupt JSON
    registry_path.write_text("{invalid json content")

    recall.main()

    out = capsys.readouterr().out
    assert out == ""
