import os
import tempfile
from pathlib import Path

from chronicle.vault.paths import MARKER, inside_root


def is_generated(path: Path) -> bool:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, UnicodeDecodeError):
        return False
    if not lines or lines[0] != "---":
        return False
    for end, line in enumerate(lines[1:], start=1):
        if line == "---":
            return f'generated_by: "{MARKER}"' in lines[1:end]
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
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=target.parent, delete=False,
        ) as stream:
            temporary = Path(stream.name)
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
