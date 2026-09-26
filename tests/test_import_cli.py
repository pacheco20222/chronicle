import hashlib

import pytest
from sqlalchemy import select

from chronicle import embeddings, import_cli
from chronicle.storage.models import Episode, Memory, Source


def test_chunk_text_single_chunk_for_short_text():
    chunks = import_cli._chunk_text("short paragraph one.\n\nshort paragraph two.")
    assert len(chunks) == 1
    assert "short paragraph one." in chunks[0]
    assert "short paragraph two." in chunks[0]


def test_chunk_text_splits_long_text_into_multiple_chunks():
    paragraphs = [f"Paragraph number {i}." * 50 for i in range(10)]
    text = "\n\n".join(paragraphs)
    chunks = import_cli._chunk_text(text, max_chars=500)
    assert len(chunks) > 1
    rejoined = "\n\n".join(chunks)
    for p in paragraphs:
        assert p in rejoined


def test_chunk_text_empty_text_returns_no_chunks():
    assert import_cli._chunk_text("") == []


def test_import_main_creates_memories_from_file(tmp_path, service):
    file_path = tmp_path / "test_import.md"
    file_path.write_text("First paragraph about the test project.\n\nSecond paragraph with more detail.")

    import_cli.main([str(file_path), "--project", "chronicle-test", "--type", "note"])

    results = service.search(embeddings.embed_text("test project"), "chronicle-test")
    assert any("First paragraph about the test project" in r["content"] for r in results)


def test_import_main_rejects_invalid_type(tmp_path):
    file_path = tmp_path / "test_import.md"
    file_path.write_text("content")

    with pytest.raises(ValueError):
        import_cli.main([str(file_path), "--project", "chronicle-test", "--type", "nonsense"])


def test_import_main_directory_creates_one_episode_backed_memory_per_file(tmp_path, service, monkeypatch, capsys):
    monkeypatch.setattr(import_cli.embeddings, "embed_text", lambda text: [1.0])
    folder = tmp_path / "notes"
    folder.mkdir()
    (folder / "nested").mkdir()
    files = {
        folder / "first.md": "first folder note",
        folder / "second.txt": "second folder note",
        folder / "nested" / "third.md": "third folder note",
    }
    for path, content in files.items():
        path.write_text(content)

    import_cli.main([str(folder), "--project", "chronicle-test", "--type", "note"])

    with service.repository.session_factory() as session:
        memories = list(session.scalars(select(Memory).order_by(Memory.created_at)).all())
        sources = list(session.scalars(select(Source)).all())
        episodes = list(session.scalars(select(Episode)).all())

    assert len(memories) == len(files)
    assert len(sources) == len(files)
    assert len(episodes) == len(files)
    for path, content in files.items():
        memory = next(row for row in memories if row.source_record.locator == str(path.resolve()))
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        assert memory.content == content
        assert memory.episode_record is not None
        assert memory.episode_record.source_id == memory.source_id
        assert memory.episode_record.title == f"{path.name} sha256:{content_hash[:16]}"
    assert capsys.readouterr().out.endswith("Scanned 3 files: 3 ingested, 0 unchanged.\n")


def test_import_main_directory_skips_unchanged_files(tmp_path, service, monkeypatch, capsys):
    monkeypatch.setattr(import_cli.embeddings, "embed_text", lambda text: [1.0])
    folder = tmp_path / "notes"
    folder.mkdir()
    (folder / "first.md").write_text("first folder note")
    (folder / "second.txt").write_text("second folder note")

    import_cli.main([str(folder), "--project", "chronicle-test", "--type", "note"])
    first_ids = {row.id for row in service.repository.all("chronicle-test")}
    capsys.readouterr()

    import_cli.main([str(folder), "--project", "chronicle-test", "--type", "note"])

    assert {row.id for row in service.repository.all("chronicle-test")} == first_ids
    assert capsys.readouterr().out == "Scanned 2 files: 0 ingested, 2 unchanged.\n"


def test_import_main_directory_changed_file_supersedes_only_previous_version(
    tmp_path, service, monkeypatch
):
    monkeypatch.setattr(import_cli.embeddings, "embed_text", lambda text: [1.0])
    folder = tmp_path / "notes"
    folder.mkdir()
    changed_path = folder / "changed.md"
    unchanged_path = folder / "unchanged.txt"
    changed_path.write_text("version one")
    unchanged_path.write_text("unchanged content")

    import_cli.main([str(folder), "--project", "chronicle-test", "--type", "note"])
    old_rows = {row.source_record.locator: row for row in service.repository.all("chronicle-test")}
    old_changed = old_rows[str(changed_path.resolve())]
    old_unchanged = old_rows[str(unchanged_path.resolve())]

    changed_path.write_text("version two")
    import_cli.main([str(folder), "--project", "chronicle-test", "--type", "note"])

    rows = {row.source_record.locator: row for row in service.repository.all("chronicle-test")}
    current_changed = service.repository.get_active_by_source_locator("chronicle-test", str(changed_path.resolve()))
    assert len(service.repository.all("chronicle-test")) == 3
    assert current_changed is not None
    assert current_changed.id != old_changed.id
    assert service.repository.get(old_changed.id).status == "superseded"
    assert rows[str(unchanged_path.resolve())].id == old_unchanged.id
    with service.repository.session_factory() as session:
        assert len(session.scalars(select(Source)).all()) == 2
        assert len(session.scalars(select(Episode)).all()) == 3
    assert rows[str(changed_path.resolve())].episode_record.title == (
        f"changed.md sha256:{hashlib.sha256(b'version two').hexdigest()[:16]}"
    )


def test_import_main_directory_skips_hidden_and_unsupported_files(tmp_path, service, monkeypatch):
    monkeypatch.setattr(import_cli.embeddings, "embed_text", lambda text: [1.0])
    folder = tmp_path / "notes"
    hidden_folder = folder / ".hidden"
    folder.mkdir()
    hidden_folder.mkdir()
    (folder / "visible.md").write_text("visible")
    (folder / ".hidden.md").write_text("hidden file")
    (hidden_folder / "nested.md").write_text("hidden directory")
    (folder / "image.png").write_text("not imported")

    import_cli.main([str(folder), "--project", "chronicle-test", "--type", "note"])

    rows = service.repository.all("chronicle-test")
    assert len(rows) == 1
    assert rows[0].source_record.locator == str((folder / "visible.md").resolve())


def test_import_main_directory_hashes_full_content_without_truncating(tmp_path, service, monkeypatch, capsys):
    monkeypatch.setattr(import_cli.embeddings, "embed_text", lambda text: [1.0])
    folder = tmp_path / "notes"
    folder.mkdir()
    path = folder / "large.md"
    content = "x" * 24001
    path.write_text(content)

    import_cli.main([str(folder), "--project", "chronicle-test", "--type", "note"])

    row = service.repository.all("chronicle-test")[0]
    assert row.content == content
    assert row.episode_record.title == f"large.md sha256:{hashlib.sha256(content.encode()).hexdigest()[:16]}"
    assert capsys.readouterr().out == "Scanned 1 files: 1 ingested, 0 unchanged.\n"


def test_import_directory_file_at_exact_threshold_stays_single_chunk(tmp_path, service, monkeypatch):
    from chronicle import import_cli
    from chronicle.core import runtime

    monkeypatch.setattr(runtime, "_runtime", service)
    exact = tmp_path / "exact.md"
    # Exactly _DOCS_CHUNK_MAX_CHARS characters, no paragraph break, so
    # _chunk_text has nothing to split on and must not produce a
    # trailing near-empty chunk.
    exact.write_text("a" * import_cli._DOCS_CHUNK_MAX_CHARS)

    import_cli._import_directory(str(tmp_path), "p", "note")

    rows = service.repository.all("p")
    assert len(rows) == 1
    assert rows[0].chunk_index is None


def test_import_directory_file_one_over_threshold_splits_cleanly(tmp_path, service, monkeypatch):
    from chronicle import import_cli
    from chronicle.core import runtime

    monkeypatch.setattr(runtime, "_runtime", service)
    over = tmp_path / "over.md"
    half = import_cli._DOCS_CHUNK_MAX_CHARS // 2
    over.write_text(("a" * half) + "\n\n" + ("b" * (half + 10)))

    import_cli._import_directory(str(tmp_path), "p", "note")

    rows = [r for r in service.repository.all("p") if r.status == "active"]
    assert len(rows) == 2
    assert all(r.content.strip() for r in rows)
    assert [r.chunk_index for r in sorted(rows, key=lambda r: r.chunk_index)] == [0, 1]


def test_import_directory_chunks_large_file(tmp_path, service, monkeypatch):
    from chronicle import import_cli
    from chronicle.core import runtime

    monkeypatch.setattr(runtime, "_runtime", service)
    big = tmp_path / "big.md"
    big.write_text(("word " * 3000) + "\n\n" + ("more " * 3000))

    import_cli._import_directory(str(tmp_path), "p", "note")

    source = service.repository.database.session_factory().execute(
        __import__("sqlalchemy").select(__import__("chronicle.storage.models", fromlist=["Source"]).Source)
    ).scalars().all()
    assert len(source) == 1
    chunks = service.repository.get_by_source(source[0].id)
    assert len(chunks) > 1
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_import_directory_small_file_stays_single_row(tmp_path, service, monkeypatch):
    from chronicle import import_cli
    from chronicle.core import runtime

    monkeypatch.setattr(runtime, "_runtime", service)
    small = tmp_path / "small.md"
    small.write_text("just a short note")

    import_cli._import_directory(str(tmp_path), "p", "note")

    rows = service.repository.all("p")
    assert len(rows) == 1
    assert rows[0].chunk_index is None


def test_import_directory_rescanning_unchanged_large_file_is_noop(tmp_path, service, monkeypatch):
    from chronicle import import_cli
    from chronicle.core import runtime

    monkeypatch.setattr(runtime, "_runtime", service)
    big = tmp_path / "big.md"
    big.write_text(("word " * 3000) + "\n\n" + ("more " * 3000))

    import_cli._import_directory(str(tmp_path), "p", "note")
    first_pass_count = len(service.repository.all("p"))

    import_cli._import_directory(str(tmp_path), "p", "note")
    assert len(service.repository.all("p")) == first_pass_count


def test_import_directory_changed_large_file_supersedes_all_chunks(tmp_path, service, monkeypatch):
    from chronicle import import_cli
    from chronicle.core import runtime

    monkeypatch.setattr(runtime, "_runtime", service)
    big = tmp_path / "big.md"
    big.write_text(("word " * 3000) + "\n\n" + ("more " * 3000))
    import_cli._import_directory(str(tmp_path), "p", "note")
    old_active = [r for r in service.repository.all("p") if r.status == "active"]

    big.write_text(("changed " * 3000) + "\n\n" + ("content " * 3000))
    import_cli._import_directory(str(tmp_path), "p", "note")

    all_rows = {r.id: r for r in service.repository.all("p")}
    for old in old_active:
        assert all_rows[old.id].status == "superseded"
    new_active = [r for r in all_rows.values() if r.status == "active"]
    assert len(new_active) >= 1


def test_chunk_text_default_matches_new_token_budget():
    paragraph = "x" * 100
    text = "\n\n".join([paragraph] * 250)  # 25,000+ chars of content
    chunks = import_cli._chunk_text(text)
    assert len(chunks) <= 2
