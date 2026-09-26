import pytest

from mnemo import embeddings, import_cli


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

    import_cli.main([str(file_path), "--project", "mnemo-test", "--type", "note"])

    results = service.search(embeddings.embed_text("test project"), "mnemo-test")
    assert any("First paragraph about the test project" in r["content"] for r in results)


def test_import_main_rejects_invalid_type(tmp_path):
    file_path = tmp_path / "test_import.md"
    file_path.write_text("content")

    with pytest.raises(ValueError):
        import_cli.main([str(file_path), "--project", "mnemo-test", "--type", "nonsense"])


def test_chunk_text_default_matches_new_token_budget():
    paragraph = "x" * 100
    text = "\n\n".join([paragraph] * 250)  # 25,000+ chars of content
    chunks = import_cli._chunk_text(text)
    assert len(chunks) <= 2
