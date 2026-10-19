import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import select

from chronicle import console, import_cli, recall
from chronicle.storage.models import Memory

SCRIPTS = Path(__file__).parents[1] / "scripts"
NON_CP1252 = "fix login → retest ✓ pollo \U0001F414"


def _cp1252_stream():
    # What Windows gives a Python process whose stdout is a pipe.
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252")


def test_use_utf8_output_lets_cp1252_streams_print_any_character(monkeypatch):
    stdout, stderr = _cp1252_stream(), _cp1252_stream()
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)

    console.use_utf8_output()
    print(NON_CP1252)
    print(NON_CP1252, file=sys.stderr)

    for stream in (stdout, stderr):
        stream.flush()
        assert stream.buffer.getvalue().decode("utf-8").rstrip("\r\n") == NON_CP1252


def test_use_utf8_output_leaves_streams_without_reconfigure_alone(monkeypatch):
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)

    console.use_utf8_output()

    assert sys.stdout is stdout


def test_recall_hook_survives_non_cp1252_memories(monkeypatch):
    stdout = _cp1252_stream()
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setenv("CHRONICLE_PROJECT", "chronicle-test")
    monkeypatch.setattr(recall, "latest_checkpoint", lambda project: f"[Chronicle] LATEST CHECKPOINT — {NON_CP1252}")
    monkeypatch.setattr(recall, "overview_document", lambda project: None)

    recall.main()

    stdout.flush()
    assert NON_CP1252 in stdout.buffer.getvalue().decode("utf-8")


def _imported_contents(service):
    with service.repository.session_factory() as session:
        return [memory.content for memory in session.scalars(select(Memory)).all()]


def test_import_strips_utf8_bom(tmp_path, service, monkeypatch):
    monkeypatch.setattr(import_cli.embeddings, "embed_text", lambda text: [1.0])
    path = tmp_path / "bom.md"
    path.write_bytes("﻿notas del año".encode("utf-8"))

    import_cli.main([str(path), "--project", "chronicle-test", "--type", "note"])

    assert _imported_contents(service) == ["notas del año"]


def test_import_reads_legacy_ansi_files(tmp_path, service, monkeypatch, capsys):
    monkeypatch.setattr(import_cli.embeddings, "embed_text", lambda text: [1.0])
    folder = tmp_path / "notes"
    folder.mkdir()
    (folder / "ansi.txt").write_bytes("café — año".encode("cp1252"))

    import_cli.main([str(folder), "--project", "chronicle-test", "--type", "note"])

    assert _imported_contents(service) == ["café — año"]
    assert "Windows-1252" in capsys.readouterr().err


def test_import_normalizes_crlf_so_paragraph_chunking_still_works(tmp_path):
    path = tmp_path / "crlf.md"
    path.write_bytes(b"first\r\n\r\nsecond")

    assert import_cli._chunk_text(import_cli._read_text(str(path)), max_chars=8) == ["first", "second"]


POWERSHELL_SCRIPTS = sorted(SCRIPTS.glob("*.ps1"))


@pytest.mark.parametrize("script", POWERSHELL_SCRIPTS, ids=lambda p: p.name)
def test_powershell_scripts_are_ascii(script):
    # Windows PowerShell 5.1 reads BOM-less scripts as ANSI: a UTF-8 em dash
    # decodes to a curly quote there, which ends the string and breaks parsing.
    script.read_bytes().decode("ascii")


@pytest.mark.parametrize("script", POWERSHELL_SCRIPTS, ids=lambda p: p.name)
def test_powershell_scripts_avoid_powershell_7_only_parameters(script):
    code = [line for line in script.read_text(encoding="ascii").splitlines() if not line.lstrip().startswith("#")]
    assert not any("-AsArray" in line for line in code)


@pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell.exe"), reason="needs Windows PowerShell 5.1")
@pytest.mark.parametrize("script", POWERSHELL_SCRIPTS, ids=lambda p: p.name)
def test_powershell_scripts_parse_in_windows_powershell(script):
    check = (
        "$e = $null; "
        f"[void][Management.Automation.Language.Parser]::ParseFile('{script}', [ref]$null, [ref]$e); "
        "$e | ForEach-Object { $_.Message }"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", check],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == ""


def _named_pipe_client(name):
    """Open the client end of a fresh Windows named pipe as a file object."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateNamedPipeW.restype = wintypes.HANDLE
    kernel32.CreateNamedPipeW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
        wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    path = "\\\\.\\pipe\\" + name
    server = kernel32.CreateNamedPipeW(path, 3, 0, 1, 4096, 4096, 0, None)  # PIPE_ACCESS_DUPLEX
    assert server and server != wintypes.HANDLE(-1).value
    client = kernel32.CreateFileW(path, 0x80000000, 0, None, 3, 0, None)  # GENERIC_READ, OPEN_EXISTING
    assert client and client != wintypes.HANDLE(-1).value
    return open(msvcrt.open_osfhandle(client, os.O_RDONLY), "r"), server


@pytest.mark.skipif(sys.platform != "win32", reason="Windows named pipes")
def test_mintty_pty_pipe_counts_as_interactive():
    stream, _server = _named_pipe_client(f"msys-dd50a72ab4668b33-pty{os.getpid() % 1000}-from-master")
    try:
        assert console.is_interactive(stream)
    finally:
        stream.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows named pipes")
def test_other_named_pipes_are_not_interactive():
    stream, _server = _named_pipe_client(f"msys-dd50a72ab4668b33-pipe-{os.getpid()}")
    try:
        assert not console.is_interactive(stream)
    finally:
        stream.close()


def test_mcp_style_piped_stdin_is_not_interactive():
    # How Claude Code, Cursor and Codex launch the server.
    code = "from chronicle.console import is_interactive; print(is_interactive())"
    result = subprocess.run(
        [sys.executable, "-c", code], stdin=subprocess.PIPE, capture_output=True, text=True, check=True
    )

    assert result.stdout.strip() == "False"


def test_cli_commands_do_not_print_migration_logs(tmp_path):
    # A fresh database runs every migration; none of that should reach the
    # person who typed `chronicle scope list`.
    env = dict(
        os.environ,
        CHRONICLE_SQLITE_PATH=str(tmp_path / "c.db"),
        CHRONICLE_REGISTRY_PATH=str(tmp_path / "projects.json"),
    )
    code = "import sys; sys.argv = ['chronicle', 'scope', 'list']; from chronicle import cli; cli.main()"
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)

    assert "alembic" not in result.stderr
    assert (tmp_path / "c.db").exists()


def test_embeddings_silence_the_windows_symlink_warning(monkeypatch):
    import types

    from chronicle import embeddings

    class FakeModel:
        def __init__(self, **kwargs):
            pass

        def embed(self, texts):
            import numpy

            return iter([numpy.zeros(3)])

    monkeypatch.delenv("HF_HUB_DISABLE_SYMLINKS_WARNING", raising=False)
    monkeypatch.setitem(sys.modules, "fastembed", types.SimpleNamespace(TextEmbedding=FakeModel))
    monkeypatch.setattr(embeddings, "_model", None)

    embeddings.embed_text("x")

    assert os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] == "1"
