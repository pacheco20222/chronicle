import os
import uuid
from pathlib import Path

from chronicle.vault.paths import MARKER, inside_root


def is_generated(path: Path) -> bool:
    try:
        with path.open("rb") as stream:
            header = stream.read(8192)
        lines = header.split(b"\n")
        if len(header) == 8192:
            lines = lines[:-1]  # A truncated line cannot close frontmatter.
    except OSError:
        return False
    if not lines or lines[0].rstrip(b"\r") != b"---":
        return False
    for end, line in enumerate(lines[1:], start=1):
        if line.rstrip(b"\r") == b"---":
            return f'generated_by: "{MARKER}"'.encode() in [line.rstrip(b"\r") for line in lines[1:end]]
    return False


def write_page(vault: Path, path: Path, text: str) -> bool:
    target = inside_root(vault, path)
    if target.exists():
        if not is_generated(target):
            return False
        if target.read_text(encoding="utf-8") == text:
            return True
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        candidate = target.parent / f".{uuid.uuid4().hex}.tmp"
        descriptor = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        temporary = candidate
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return True


def delete_page(vault: Path, path: Path) -> bool:
    target = inside_root(vault, path)
    if not is_generated(target):
        return False
    target.unlink()
    return True
