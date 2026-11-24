import os
from pathlib import Path

import pytest

from chronicle import config
from chronicle.vault import paths, settings, writer


MARKED = '---\ngenerated_by: "chronicle"\n---\nHello\n'


def test_wikilink_strips_delimiters_from_target_and_alias():
    assert paths.wikilink('Chronicle/[p]|x', '[title]|x') == '[[Chronicle/px|titlex]]'


def test_project_folder_names_preserve_distinct_raw_names(tmp_path):
    import hashlib

    for project in ['a/b', 'a:b', ' CON ', 'x' * 100]:
        expected = paths.safe_name(project, 80) + '-' + hashlib.sha256(project.encode()).hexdigest()[:8]
        assert paths.project_folder_name(project) == expected
        assert paths.project_dir(tmp_path, project).name == expected
    assert paths.project_folder_name('ab') == 'ab'
    assert paths.project_dir(tmp_path, 'a/b') != paths.project_dir(tmp_path, 'ab')


def test_shared_memory_title_is_trimmed_and_bounded():
    assert paths.memory_title(' \n  Title  \nrest') == 'Title'
    assert paths.memory_title(' \n') == 'untitled'
    assert paths.memory_title('x' * 100) == 'x' * 80


def test_marker_read_is_bounded_and_handles_os_errors(tmp_path, monkeypatch):
    assert writer.is_generated(tmp_path) is False
    page = tmp_path / 'page.md'
    page.write_text('---\ntitle: "' + 'x' * 8192 + '"\ngenerated_by: "chronicle"\n---\n')
    assert writer.is_generated(page) is False

    def denied(*args, **kwargs):
        raise PermissionError('denied')

    monkeypatch.setattr(Path, 'open', denied)
    assert writer.is_generated(page) is False


def test_marker_does_not_decode_body_past_eight_kib(tmp_path):
    page = tmp_path / 'page.md'
    page.write_bytes(MARKED.encode() + b'x' * 8192 + b'\xff')
    assert writer.is_generated(page) is True


@pytest.mark.parametrize('mask, expected', [(0o022, 0o644), (0o077, 0o600), (0o002, 0o644)])
def test_written_page_permissions_respect_umask(tmp_path, mask, expected):
    previous = os.umask(mask)
    try:
        page = paths.memory_file(tmp_path, 'p', 'note')
        writer.write_page(tmp_path, page, MARKED)
        assert page.stat().st_mode & 0o777 == expected
    finally:
        os.umask(previous)


@pytest.mark.parametrize('value', [None, 'p', 42, {}, ['p', 1]])
def test_invalid_vault_projects_returns_empty(value):
    config.write_config({'vault_projects': value})
    assert settings.vault_projects() == []


def test_bracketed_names_match_wikilink_targets(tmp_path):
    folder = paths.project_dir(tmp_path, '[p]').name
    stem = paths.memory_stem('note', '[Title]', '12345678')
    assert '[' not in folder and ']' not in folder
    assert '[' not in stem and ']' not in stem
    target = f'Chronicle/{folder}/memories/{stem}'
    assert paths.wikilink(target, '[Title]') == f'[[{target}|Title]]'


def test_partial_closing_delimiter_at_read_boundary_is_not_a_marker(tmp_path):
    page = tmp_path / 'page.md'
    prefix = '---\ngenerated_by: "chronicle"\n'
    padding = 'x' * (8192 - len(prefix) - 4)
    page.write_text(prefix + padding + '\n---not-a-delimiter\n')
    assert writer.is_generated(page) is False
