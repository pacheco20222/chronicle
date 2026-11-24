import os
import time
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path

import pytest

from chronicle import registry
from chronicle.vault import render


def catalog():
    from chronicle.vault import catalog
    return catalog


def put(folder, relative, content='data'):
    path = folder / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def test_scan_skips_hidden_and_importer_directories(tmp_path):
    from chronicle.import_cli import SKIP_DIRS

    folder = tmp_path / 'project'
    put(folder, 'invoices/Payment-Terms.pdf')
    for name in SKIP_DIRS | {'.git', '.hidden'}:
        put(folder, f'{name}/skip.pdf')
    put(folder, '.secret.pdf')
    registry.register(folder, 'p')
    entries, truncated = catalog().list_files('p')
    assert [entry.relative_path for entry in entries] == ['invoices/Payment-Terms.pdf']
    assert truncated is False
    assert catalog().list_files('p', query='PAY') == (entries, False)
    assert catalog().list_files('p', query='absent') == ([], False)


def test_entry_metadata_is_frozen_and_utc(tmp_path, monkeypatch):
    folder = tmp_path / 'project'
    path = put(folder, 'terms.pdf', 'hello')
    instant = datetime(2026, 11, 23, 0, 30, tzinfo=timezone.utc).timestamp()
    os.utime(path, (instant, instant))
    registry.register(folder, 'p')
    try:
        with monkeypatch.context() as clock:
            clock.setenv('TZ', 'UTC+12')
            time.tzset()
            entries, _ = catalog().list_files('p')
    finally:
        time.tzset()
    entry = entries[0]
    assert entry == catalog().CatalogEntry(str(folder), 'terms.pdf', str(path), 5, '2026-11-23')
    with pytest.raises(FrozenInstanceError):
        entry.size = 9


def test_global_order_and_cap_are_independent_of_walk_order(tmp_path, monkeypatch):
    folders = [tmp_path / 'z', tmp_path / 'a']
    for folder in folders:
        for name in ['z.pdf', 'a/child.pdf', 'a.pdf', 'b.pdf', 'c.pdf']:
            put(folder, name)
    monkeypatch.setattr(registry, 'list_projects', lambda: {'p': list(map(str, folders))})
    entries, truncated = catalog().list_files('p', limit=3)
    assert [(e.folder, e.relative_path) for e in entries] == [
        (str(folders[1]), name) for name in ['a.pdf', 'a/child.pdf', 'b.pdf']
    ]
    assert truncated is True
    all_entries, truncated = catalog().list_files('p', limit=10)
    assert len(all_entries) == 10
    assert truncated is False
    assert catalog().list_files('p', limit=0) == ([], True)
    assert catalog().list_files('missing', limit=0) == ([], False)
    with pytest.raises(ValueError):
        catalog().list_files('p', limit=-1)


def test_symlink_boundaries_and_nonregular_files(tmp_path):
    folder = tmp_path / 'project'
    inside = put(folder, 'inside.pdf')
    outside = put(tmp_path / 'outside', 'secret.pdf')
    (folder / 'allowed.pdf').symlink_to(inside)
    (folder / 'escape.pdf').symlink_to(outside)
    (folder / 'broken.pdf').symlink_to(folder / 'missing.pdf')
    (folder / 'linked-dir').symlink_to(outside.parent, target_is_directory=True)
    (folder / 'loop').symlink_to(folder, target_is_directory=True)
    os.mkfifo(folder / 'pipe')
    registry.register(folder, 'p')
    entries, _ = catalog().list_files('p')
    assert [e.relative_path for e in entries] == ['allowed.pdf', 'inside.pdf']


def test_unreadable_and_missing_paths_are_skipped(tmp_path, monkeypatch):
    folder = tmp_path / 'project'
    put(folder, 'ok.pdf')
    put(folder, 'denied/secret.pdf')
    put(folder, 'vanished.pdf')
    registry.register(folder, 'p')
    registry.register(tmp_path / 'missing', 'p')
    original_scandir = os.scandir
    original_stat = Path.stat

    def scandir(path):
        if Path(path).name == 'denied':
            raise PermissionError('denied')
        return original_scandir(path)

    def stat(path, *args, **kwargs):
        if path.name == 'vanished.pdf':
            raise FileNotFoundError('gone')
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(os, 'scandir', scandir)
    monkeypatch.setattr(Path, 'stat', stat)
    entries, truncated = catalog().list_files('p')
    assert [e.relative_path for e in entries] == ['ok.pdf']
    assert truncated is False


def test_render_groups_folders_and_is_byte_stable(tmp_path):
    folders = [tmp_path / 'z', tmp_path / 'a']
    for folder in folders:
        put(folder, 'invoices/Payment Terms(1).PDF', 'hello')
        registry.register(folder, 'p')
    entries, _ = catalog().list_files('p')
    page = catalog().render_files('p', entries, True)
    assert 'generated_by: "chronicle"' in page
    assert page.index(str(folders[1])) < page.index(str(folders[0]))
    assert '[invoices/Payment Terms(1).PDF](file:///' in page
    assert 'Payment%20Terms%281%29.PDF)' in page
    assert 'pdf' in page and '5 bytes' in page and entries[0].modified in page
    assert 'Truncated at 2 files' in page
    assert page == catalog().render_files('p', list(reversed(entries)), True)


def test_empty_registration_and_empty_folder_differ(tmp_path):
    assert catalog().list_files('p') == ([], False)
    assert 'No project folder registered' in catalog().render_files('p', [], False)
    folder = tmp_path / 'empty'
    folder.mkdir()
    registry.register(folder, 'p')
    page = catalog().render_files('p', [], False)
    assert 'No project folder registered' not in page
    assert str(folder) in page


@pytest.mark.parametrize('name', [
    'run.sh', 'app.exe', 'page.html', 'script.py', 'extensionless',
    'bad\u2066.pdf', 'bad\u200e.pdf', 'bad\n.pdf', 'bad`.exe',
])
def test_render_unsafe_paths_are_inert(tmp_path, name):
    folder = tmp_path / 'project'
    put(folder, name)
    registry.register(folder, 'p')
    entries, _ = catalog().list_files('p')
    page = catalog().render_files('p', entries, False)
    assert 'file://' not in page
    assert '\u2066' not in page and '\u200e' not in page


@pytest.mark.parametrize('extension', sorted(render._DOCUMENT_EXTENSIONS))
def test_catalog_reuses_source_allowlist_and_uri_encoding(tmp_path, extension):
    folder = tmp_path / 'project'
    path = put(folder, f'a [b](c)#%.{extension}')
    registry.register(folder, 'p')
    entries, _ = catalog().list_files('p')
    page = catalog().render_files('p', entries, False)
    destination = path.as_uri().replace('(', '%28').replace(')', '%29')
    assert f']({destination})' in page


def test_symlink_to_executable_cannot_disguise_extension(tmp_path):
    folder = tmp_path / 'project'
    target = put(folder, 'run.sh')
    (folder / 'read.pdf').symlink_to(target)
    registry.register(folder, 'p')
    entries, _ = catalog().list_files('p')
    assert 'file://' not in catalog().render_files('p', entries, False)


def test_three_file_cap_over_five_matches(tmp_path):
    folder = tmp_path / 'project'
    for index in reversed(range(5)):
        put(folder, f'{index}.pdf')
    registry.register(folder, 'p')
    entries, truncated = catalog().list_files('p', limit=3)
    assert [entry.relative_path for entry in entries] == ['0.pdf', '1.pdf', '2.pdf']
    assert truncated is True
    assert catalog().list_files('p', query='4', limit=3)[1] is False
