import argparse
import hashlib
import os
import sys

from chronicle import config, embeddings
from chronicle.core.runtime import get_runtime


_DOCS_CHUNK_MAX_CHARS = 6000  # ~1500 tokens at ~4 chars/token


def _read_text(path: str) -> str:
    # utf-8-sig drops the BOM some Windows editors write, so it doesn't end
    # up as an invisible first character of the memory. Files saved in the
    # legacy Windows "ANSI" encoding aren't valid UTF-8; read those as
    # cp1252 rather than failing the whole import.
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(path, "r", encoding="cp1252", errors="replace") as f:
            text = f.read()
        print(f"Note: {path} is not UTF-8; read it as Windows-1252 (ANSI).", file=sys.stderr)
        return text


def _chunk_text(text: str, max_chars: int = 24000) -> list[str]:
    # ~6000 tokens at ~4 chars/token, same proportional safety margin
    # the original 6000-char/2048-token design used, scaled to
    # fastembed's 8192-token window.
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    chunks = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > max_chars and current:
            chunks.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _import_directory(path: str, project: str, type_: str) -> None:
    root = os.path.abspath(path)
    file_paths = []
    for current_root, directories, filenames in os.walk(root):
        directories[:] = sorted(name for name in directories if not name.startswith("."))
        for name in sorted(filenames):
            if name.startswith(".") or os.path.splitext(name)[1] not in {".md", ".txt"}:
                continue
            file_paths.append(os.path.abspath(os.path.join(current_root, name)))

    service = get_runtime()
    ingested = 0
    unchanged = 0
    for file_path in file_paths:
        content = _read_text(file_path)
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        episode_title = f"{os.path.basename(file_path)} sha256:{content_hash[:16]}"
        active_chunks = service.repository.get_active_by_source_locator_all(project, file_path)
        if active_chunks and active_chunks[0].episode_record and active_chunks[0].episode_record.title == episode_title:
            unchanged += 1
            continue

        for old in active_chunks:
            service.set_status(old.id, "superseded")

        episode = service.repository.create_episode(
            project=project,
            locator=file_path,
            title=episode_title,
        )
        pieces = _chunk_text(content, max_chars=_DOCS_CHUNK_MAX_CHARS)
        for index, piece in enumerate(pieces):
            vector = embeddings.embed_or_empty(piece)
            service.add_memory(
                vector,
                piece,
                project,
                type_,
                source=file_path,
                episode_id=episode.id,
                chunk_index=index if len(pieces) > 1 else None,
            )
        ingested += 1

    print(f"Scanned {len(file_paths)} files: {ingested} ingested, {unchanged} unchanged.")


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="chronicle import")
    parser.add_argument("file")
    parser.add_argument("--project", required=True)
    parser.add_argument("--type", required=True, dest="type_")
    args = parser.parse_args(argv)

    config.validate_type(args.type_)

    if os.path.isdir(args.file):
        _import_directory(args.file, args.project, args.type_)
        return

    text = _read_text(args.file)

    chunks = _chunk_text(text)
    service = get_runtime()

    for i, chunk in enumerate(chunks, start=1):
        vector = embeddings.embed_or_empty(chunk)
        source = f"{args.file} (chunk {i}/{len(chunks)})" if len(chunks) > 1 else args.file
        service.add_memory(vector, chunk, args.project, args.type_, source=source)

    print(f"Imported {len(chunks)} memories from {args.file} into project '{args.project}'")
