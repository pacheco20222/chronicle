import sys


def use_utf8_output() -> None:
    """Write stdout/stderr as UTF-8 regardless of the platform default.

    On Windows, piped output (a SessionStart hook, `chronicle ... > file`)
    defaults to the ANSI code page (e.g. cp1252), which can't encode common
    memory content like arrows or emoji: print() raises UnicodeEncodeError.
    Hook readers like Claude Code decode hook output as UTF-8 anyway.
    """
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if encoding == "utf8" or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue
