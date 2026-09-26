import argparse
import hashlib
import os

from chronicle import config, embeddings
from chronicle.core.runtime import get_runtime


_FOLDER_IMPORT_MAX_CHARS = 24000


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
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        episode_title = f"{os.path.basename(file_path)} sha256:{content_hash[:16]}"
        active = service.repository.get_active_by_source_locator(project, file_path)
        if active is not None and active.episode_record and active.episode_record.title == episode_title:
            unchanged += 1
            continue

        stored_content = content[:_FOLDER_IMPORT_MAX_CHARS]
        if len(content) > _FOLDER_IMPORT_MAX_CHARS:
            print(f"Truncated {file_path} to {_FOLDER_IMPORT_MAX_CHARS} characters")
        episode = service.repository.create_episode(
            project=project,
            locator=file_path,
            title=episode_title,
        )
        vector = embeddings.embed_text(stored_content)
        service.add_memory(
            vector,
            stored_content,
            project,
            type_,
            source=file_path,
            supersedes=active.id if active is not None else None,
            episode_id=episode.id,
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

    with open(args.file, "r", encoding="utf-8") as f:
        text = f.read()

    chunks = _chunk_text(text)
    service = get_runtime()

    for i, chunk in enumerate(chunks, start=1):
        vector = embeddings.embed_text(chunk)
        source = f"{args.file} (chunk {i}/{len(chunks)})" if len(chunks) > 1 else args.file
        service.add_memory(vector, chunk, args.project, args.type_, source=source)

    print(f"Imported {len(chunks)} memories from {args.file} into project '{args.project}'")
