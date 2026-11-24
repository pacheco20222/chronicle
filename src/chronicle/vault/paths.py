import hashlib
import re
import unicodedata
from pathlib import Path

MARKER = "chronicle"
CONTROL_CHARACTERS = frozenset(map(chr, range(32))) | {"\x7f", "\u2028", "\u2029"}
_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$", re.IGNORECASE)


def safe_name(text: str, max_length: int) -> str:
    if max_length < 1:
        raise ValueError("max_length must be positive")
    name = re.sub(r"\s+", "-", text.strip())
    name = "".join(
        char for char in name
        if char not in '<>:"/\\|?*[]' and unicodedata.category(char) != "Cc"
    )
    name = re.sub(r"\.{2,}", "-", name).strip(" .-") or "untitled"
    name = name[:max_length].rstrip(" .-") or "untitled"[:max_length]
    if _RESERVED.fullmatch(name.split(".", 1)[0]):
        base, dot, extension = name[:max_length - 1].partition(".")
        name = f"{base}_{dot}{extension}"
    return name


def memory_title(content: str) -> str:
    return next((line.strip()[:80] for line in content.splitlines() if line.strip()), "untitled")


def memory_stem(type_: str, content: str, memory_id: str) -> str:
    title = memory_title(content)
    type_name = safe_name(type_, 24)
    suffix = safe_name(memory_id[:8], 8)
    title = safe_name(title, 80 - len(type_name) - len(suffix) - 2)
    return f"{type_name}-{title}-{suffix}"


def chronicle_root(vault: Path) -> Path:
    return inside_root(vault, vault.expanduser().resolve() / "Chronicle")


def project_folder_name(project: str) -> str:
    name = safe_name(project, 80)
    if name != project:
        name += "-" + hashlib.sha256(project.encode("utf-8")).hexdigest()[:8]
    return name


def project_dir(vault: Path, project: str) -> Path:
    return inside_root(vault, chronicle_root(vault) / project_folder_name(project))


def memory_file(vault: Path, project: str, stem: str) -> Path:
    return inside_root(vault, project_dir(vault, project) / "memories" / f"{safe_name(stem, 80)}.md")


def strip_controls(text: str) -> str:
    return "".join(char for char in text if char not in CONTROL_CHARACTERS)


def wikilink(vault_relative_target: str, alias: str) -> str:
    delimiters = str.maketrans("", "", "|[]")
    target = strip_controls(vault_relative_target).translate(delimiters)
    title = strip_controls(alias).translate(delimiters) or target.rstrip("/").rsplit("/", 1)[-1]
    return f"[[{target}|{title}]]"


def inside_root(vault: Path, candidate: Path) -> Path:
    root = vault.expanduser().resolve() / "Chronicle"
    resolved = candidate.expanduser().resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"path {candidate} is outside {root}")
    return resolved
