import argparse

from mnemo import config, embeddings
from mnemo.core.runtime import get_runtime


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


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="mnemo import")
    parser.add_argument("file")
    parser.add_argument("--project", required=True)
    parser.add_argument("--type", required=True, dest="type_")
    args = parser.parse_args(argv)

    config.validate_type(args.type_)

    with open(args.file, "r", encoding="utf-8") as f:
        text = f.read()

    chunks = _chunk_text(text)
    service = get_runtime()

    for i, chunk in enumerate(chunks, start=1):
        vector = embeddings.embed_text(chunk)
        source = f"{args.file} (chunk {i}/{len(chunks)})" if len(chunks) > 1 else args.file
        service.add_memory(vector, chunk, args.project, args.type_, source=source)

    print(f"Imported {len(chunks)} memories from {args.file} into project '{args.project}'")
