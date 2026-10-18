import io
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
