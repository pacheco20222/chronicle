import pytest
from sqlalchemy import select

from chronicle import import_cli, server
from chronicle.storage.models import Source


@pytest.fixture(autouse=True)
def stub_embeddings(monkeypatch):
    monkeypatch.setattr(server.embeddings, "embed_or_empty", lambda text: [1.0])


@pytest.mark.parametrize("source", ["~/x/../x/terms.pdf", "invoices/terms.pdf"])
def test_memory_add_stores_a_resolved_file_reference(tmp_path, monkeypatch, service, source):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    expected = tmp_path / ("x/terms.pdf" if source.startswith("~") else source)

    added = server.memory_add("payment questions", "note", source=source)
    latest = service.get_latest("chronicle-test", "note")

    assert added["source"] == latest["source"] == str(expected)
    assert added["source_kind"] == latest["source_kind"] == "reference"


@pytest.mark.parametrize("source", ["http://example.com/a/../b?q=x#part", "https://example.com/a%20b?q=1&x=2"])
def test_memory_add_keeps_urls_verbatim(service, source):
    added = server.memory_add("linked resource", "note", source=source)
    latest = service.get_latest("chronicle-test", "note")

    assert added["source"] == latest["source"] == source
    assert latest["source_kind"] == "reference"


@pytest.mark.parametrize("source", [None, "", " \t\n"])
def test_memory_add_without_a_source_creates_no_source_row(service, source):
    added = server.memory_add("plain note", "note", source=source)
    latest = service.get_latest("chronicle-test", "note")

    assert added["source"] is latest["source"] is None
    assert added["source_kind"] is latest["source_kind"] is None
    with service.repository.session_factory() as session:
        assert session.scalars(select(Source)).all() == []


def test_importer_never_supersedes_a_reference_memory(tmp_path, service):
    folder = tmp_path / "notes"
    folder.mkdir()
    path = folder / "terms.md"
    path.write_text("first chunk\n\n" + "x" * 6000)
    reference = server.memory_add("see terms", "note", source=str(path))

    assert import_cli.import_directory(service, str(folder), "chronicle-test", "note") == (1, 1, 0)
    old_chunks = service.repository.get_active_by_source_locator_all("chronicle-test", str(path))
    assert len(old_chunks) == 2
    assert all(row.id != reference["id"] for row in old_chunks)
    assert all(row.episode_record.source_id == row.source_id for row in old_chunks)
    assert import_cli.import_directory(service, str(folder), "chronicle-test", "note") == (1, 0, 1)

    path.write_text("updated terms")
    assert import_cli.import_directory(service, str(folder), "chronicle-test", "note") == (1, 1, 0)

    assert service.repository.get(reference["id"]).status == "active"
    assert all(service.repository.get(row.id).status == "superseded" for row in old_chunks)
    current = service.repository.get_active_by_source_locator_all("chronicle-test", str(path))
    assert [row.content for row in current] == ["updated terms"]
    assert current[0].source_record.kind == "external"
    assert current[0].episode_record.source_id == current[0].source_id


@pytest.mark.parametrize("first_kind", ["reference", "external"])
def test_reference_and_import_sources_are_separate_rows(service, first_kind):
    other_kind = "external" if first_kind == "reference" else "reference"
    ids = [
        service.add_memory([1.0], "source note", "project", "note", source="/terms.md", source_kind=kind)
        for kind in [first_kind, other_kind, first_kind]
    ]
    rows = [service.repository.get(memory_id) for memory_id in ids]

    assert rows[0].source_id == rows[2].source_id
    assert rows[0].source_id != rows[1].source_id
    assert [row.source_record.kind for row in rows] == [first_kind, other_kind, first_kind]
    with service.repository.session_factory() as session:
        assert len(session.scalars(select(Source)).all()) == 2


def test_source_locator_queries_exclude_references(service):
    repository = service.repository
    service.add_memory([1.0], "reference", "project", "note", source="/terms.md", source_kind="reference")
    assert repository.get_active_by_source_locator("project", "/terms.md") is None
    assert repository.get_active_by_source_locator_all("project", "/terms.md") == []

    external_id = service.add_memory([1.0], "import", "project", "note", source="/terms.md")
    service.add_memory([1.0], "new reference", "project", "note", source="/terms.md", source_kind="reference")
    assert repository.get_active_by_source_locator("project", "/terms.md").id == external_id
    assert [row.id for row in repository.get_active_by_source_locator_all("project", "/terms.md")] == [external_id]


def test_existing_add_memory_callers_unchanged(service):
    memory_id = service.add_memory([1.0], "legacy import", "project", "note", "relative.md", "resolved")
    latest = service.get_latest("project", "note")

    assert latest["id"] == memory_id
    assert latest["source"] == "relative.md"
    assert latest["source_kind"] == "external"
    assert latest["status"] == "resolved"


def test_edit_preserves_source_and_supersede_takes_its_own_source(service):
    first = server.memory_add("first", "note", source="https://example.com/first")
    service.edit_memory(first["id"], "corrected", [1.0])
    assert service.get_latest("chronicle-test", "note")["source"] == "https://example.com/first"

    second = server.memory_add("replacement", "note", supersedes=first["id"], source="https://example.com/second")
    assert service.get_latest("chronicle-test", "note")["source"] == "https://example.com/second"
    third = server.memory_add("without reference", "note", supersedes=second["id"])
    latest = service.get_latest("chronicle-test", "note")
    assert latest["id"] == third["id"]
    assert latest["source"] is latest["source_kind"] is None
