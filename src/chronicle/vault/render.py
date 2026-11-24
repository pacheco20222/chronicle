"""Deterministic Markdown projections of serialized Chronicle memories."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PureWindowsPath
from urllib.parse import quote, urlsplit

from chronicle.vault.paths import (
    CONTROL_CHARACTERS, MARKER, project_folder_name, strip_controls, wikilink,
)

_RECENT_PER_TYPE = 5
_DOCUMENT_EXTENSIONS = frozenset(
    "pdf doc docx xls xlsx ppt pptx odt ods odp rtf txt md csv json "
    "png jpg jpeg gif webp svg mp3 mp4 mov wav".split()
)


@dataclass(frozen=True)
class LinkTarget:
    project: str
    stem: str | None
    title: str


def _frontmatter(**values) -> str:
    # JSON strings are also YAML double-quoted strings, including escaped controls.
    values["generated_by"] = MARKER
    lines = [f"{key}: {json.dumps(value, ensure_ascii=True)}" for key, value in values.items()]
    return "---\n" + "\n".join(lines) + "\n---\n\n"


def _project_link(project: str, section: str | None = None) -> str:
    folder = project_folder_name(project)
    return wikilink(f"Chronicle/{folder}/{section or folder}", section or _markdown_label(project))


def _target_link(target: LinkTarget) -> str:
    if target.stem is None:
        return f"(in project {strip_controls(target.project)}, not mirrored)"
    folder = project_folder_name(target.project)
    return wikilink(f"Chronicle/{folder}/memories/{target.stem}", target.title)


def _markdown_label(text: str) -> str:
    return strip_controls(text).translate({ord(char): "\\" + char for char in "\\[]<>`"})


def _inert_source(source: str) -> str:
    text = "".join(" " if char in CONTROL_CHARACTERS else char for char in source if char != "`")
    return f"`{text}`"


def _source_link(source: str, vault: Path | None, label: str | None = None) -> str:
    if any(char in CONTROL_CHARACTERS for char in source):
        return _inert_source(source)
    try:
        windows = PureWindowsPath(source)
        scheme = "" if windows.is_absolute() else urlsplit(source).scheme
        if scheme in {"http", "https"}:
            if source.endswith("\\"):
                return _inert_source(source)
            destination = quote(source, safe=":/?#[]@!$&'*+,;=%")
            return f"[{_markdown_label(source)}]({destination})"
        if scheme:
            return _inert_source(source)
        return _file_source_link(source, vault, label)
    except (ValueError, OSError, RuntimeError):
        return _inert_source(source)


def _file_source_link(source: str, vault: Path | None, label: str | None = None) -> str:
    windows = PureWindowsPath(source)
    foreign_windows = os.name != "nt" and windows.is_absolute()
    native = Path(source).expanduser()
    if not foreign_windows and not native.is_absolute():
        return _inert_source(source)
    path = windows if foreign_windows else native.resolve()
    if any(char in CONTROL_CHARACTERS for char in str(path)):
        return _inert_source(str(path))
    exists = False if foreign_windows else path.exists()
    directory = source.endswith(("/", "\\")) if foreign_windows else path.is_dir()
    suffix = " (file not found)" if not exists else ""
    if directory or path.suffix.lower().lstrip(".") not in _DOCUMENT_EXTENSIONS:
        return _inert_source(str(path)) + suffix
    resolved_vault = None if foreign_windows or vault is None else vault.resolve()
    if resolved_vault is not None and path.is_relative_to(resolved_vault):
        relative = path.relative_to(resolved_vault)
        target = relative.with_suffix("") if relative.suffix.lower() == ".md" else relative
        link = wikilink(target.as_posix(), _markdown_label(path.name))
    else:
        uri = path.as_uri().replace("(", "%28").replace(")", "%29")
        link = f"[{_markdown_label(label if label is not None else path.name)}]({uri})"
    return link + suffix


def _memory_links(memory: dict, links: dict[str, LinkTarget]) -> list[tuple[str, str]]:
    result = [("Project", _project_link(memory["project"]))]
    predecessor = memory.get("supersedes")
    if predecessor:
        result.append(("Replaces", _target_link(links[predecessor])))
    for relation in memory.get("relations") or []:
        label = "Replaces" if relation["type"] == "supersedes" else relation["type"]
        entry = (label, _target_link(links[relation["target"]]))
        if entry not in result:
            result.append(entry)
    for relation in memory.get("_inbound") or []:
        label = "Replaced by" if relation["type"] == "supersedes" else f'{relation["type"]} (from)'
        entry = (label, _target_link(links[relation["source"]]))
        if entry not in result:
            result.append(entry)
    for memory_id in memory.get("_similar") or []:
        result.append(("similar", _target_link(links[memory_id])))
    return result


def render_memory(memory: dict, links: dict[str, LinkTarget], vault: Path) -> str:
    properties = dict(chronicle_id=memory["id"], project=memory["project"],
                      type=memory["type"], status=memory["status"],
                      created=memory["created_at"], updated=memory["updated_at"])
    for key in ("confidence", "source"):
        if memory.get(key) is not None:
            properties[key] = memory[key]
    entries = _memory_links(memory, links)
    banner = {"wrong": "Marked wrong", "deleted": "Retracted"}.get(memory["status"])
    if memory["status"] == "superseded":
        successors = [value for label, value in entries if label == "Replaced by"]
        if successors:
            banner = "Replaced by " + ", ".join(successors)
    if memory.get("source"):
        entries.append(("Source", _source_link(memory["source"], vault)))
    body = (f"> {banner}\n\n" if banner else "") + memory["content"]
    return _frontmatter(**properties) + body + "\n\n## Links\n\n" + "\n".join(
        f"{label}: {value}" for label, value in entries
    ) + "\n"


def _timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def render_log(project: str, memories: list[dict], links: dict[str, LinkTarget]) -> str:
    events = []
    for memory in memories:
        events.append((memory["created_at"], "created", memory))
        status = memory["status"]
        if status in {"superseded", "wrong", "deleted"}:
            at = memory.get("invalid_at") if status != "deleted" else memory.get("updated_at")
            if at:
                event = {"superseded": "superseded", "wrong": "marked wrong", "deleted": "retracted"}[status]
                events.append((at, event, memory))
    events.sort(key=lambda event: (_timestamp(event[0]), event[2]["id"], event[1]), reverse=True)
    lines = [f"# {_markdown_label(project)} log\n"]
    for at, event, memory in events:
        target = links[memory['id']]
        date = _timestamp(at).date().isoformat()
        lines.append(f"## [{date}] {event} | {strip_controls(target.title)}\n\n{_target_link(target)}\n")
    return _frontmatter(project=project) + "\n".join(lines) + "\n"


def render_project(
    project: str, overview: str | None, memories: list[dict], vault: Path,
    links: dict[str, LinkTarget],
) -> str:
    lines = [f"# {_markdown_label(project)}\n"]
    if overview:
        lines.append(overview + "\n")
    lines.append(f"{_project_link(project, 'log')} · {_project_link(project, 'files')}\n")
    for field, heading in (("type", "By type"), ("status", "By status")):
        lines.append(f"## {heading}\n")
        lines.extend(f"- {name}: {count}" for name, count in sorted(Counter(m[field] for m in memories).items()))
        lines.append("")
    lines.append("## Recent memories\n")
    for type_ in sorted({m["type"] for m in memories}):
        lines.append(f"### {strip_controls(type_)}\n")
        recent = sorted((m for m in memories if m["type"] == type_),
                        key=lambda m: (_timestamp(m["created_at"]), m["id"]), reverse=True)
        lines.extend(f"- {_target_link(links[m['id']])}" for m in recent[:_RECENT_PER_TYPE])
        lines.append("")
    return _frontmatter(project=project) + "\n".join(lines) + "\n"


def render_index(projects: list[tuple[str, str]]) -> str:
    lines = ["# Chronicle\n"]
    for project, summary in sorted(projects):
        lines.append(f"- {_project_link(project)} — {' '.join(summary.splitlines())}")
    return _frontmatter() + "\n".join(lines) + "\n"
