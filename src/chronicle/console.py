import re
import sys

# mintty (old Git Bash, MSYS2, Cygwin) gives programs a named pipe instead of
# a console, so isatty() is False even when a person is typing.
_MSYS_PTY_PIPE = re.compile(r"\\(cygwin|msys)-[0-9a-f]+-pty\d+-(from|to)-master")


def _windows_pipe_name(stream) -> str | None:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    FILE_TYPE_PIPE = 3
    FILE_NAME_INFO_CLASS = 2

    class FILE_NAME_INFO(ctypes.Structure):
        _fields_ = [("FileNameLength", wintypes.DWORD), ("FileName", wintypes.WCHAR * 1024)]

    try:
        handle = msvcrt.get_osfhandle(stream.fileno())
    except (AttributeError, OSError, ValueError):
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetFileType.argtypes = [wintypes.HANDLE]
    kernel32.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    if kernel32.GetFileType(handle) != FILE_TYPE_PIPE:
        return None
    info = FILE_NAME_INFO()
    if not kernel32.GetFileInformationByHandleEx(handle, FILE_NAME_INFO_CLASS, ctypes.byref(info), ctypes.sizeof(info)):
        return None
    return info.FileName[: info.FileNameLength // 2]


def is_interactive(stream=None) -> bool:
    """True when a person is typing into `stream` (default stdin)."""
    stream = sys.stdin if stream is None else stream
    try:
        if stream is not None and stream.isatty():
            return True
    except (AttributeError, ValueError):
        return False
    if sys.platform != "win32" or stream is None:
        return False
    name = _windows_pipe_name(stream)
    return name is not None and _MSYS_PTY_PIPE.search(name) is not None


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
