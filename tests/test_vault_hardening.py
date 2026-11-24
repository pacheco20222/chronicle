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


def test_wikilink_removes_newlines_without_markdown_injection():
    assert paths.wikilink('a\nb', 'x\n\n# h') == '[[ab|x# h]]'


@pytest.mark.parametrize('control', [chr(value) for value in range(32)] + ['\x7f', '\u2028', '\u2029'])
def test_wikilink_and_markdown_label_remove_controls(control):
    from chronicle.vault.render import _markdown_label

    assert paths.wikilink(f'a{control}b', f'x{control}y') == '[[ab|xy]]'
    assert _markdown_label(f'<x{control}y>`') == '\\<xy\\>\\`'


@pytest.mark.parametrize('alias', ['', '\n\x00\u2028\u2029', '|[\t]'])
def test_empty_sanitized_wikilink_alias_falls_back_to_target_segment(alias):
    assert paths.wikilink('Chronicle/p/no\nte', alias) == '[[Chronicle/p/note|note]]'


def test_project_and_log_titles_remove_controls(tmp_path):
    from chronicle.vault.render import LinkTarget, render_log, render_project

    project = 'p\n\n# injected\u2028\t'
    title = 'Title\n\n# injected\u2029\x7f'
    item = dict(id='id', project=project, type='note', content='Body', status='active',
                created_at='2026-11-23T00:00:00+00:00')
    links = {'id': LinkTarget(project, 'note', title)}
    project_page = render_project(project, None, [item], tmp_path, links)
    log_page = render_log(project, [item], links)
    assert '# p# injected\n' in project_page
    assert '# p# injected log\n' in log_page
    assert 'created | Title# injected\n' in log_page
    for page in (project_page, log_page):
        assert '\n# injected' not in page
        assert '\u2028' not in page and '\u2029' not in page and '\x7f' not in page
        assert '|Title# injected]]' in page


def test_unmirrored_project_label_removes_controls_without_leaking_title():
    from chronicle.vault.render import LinkTarget, _target_link

    assert _target_link(LinkTarget('p\n\n# injected', None, 'Secret')) == (
        '(in project p# injected, not mirrored)'
    )


def test_unresolvable_home_source_does_not_abort_memory_page(tmp_path, monkeypatch):
    from chronicle.vault.render import render_memory

    def unavailable_home(*args, **kwargs):
        raise RuntimeError('Could not determine home directory.')

    monkeypatch.setattr(Path, 'expanduser', unavailable_home)
    item = dict(id='id', project='p', type='note', status='active', content='Body survives',
                created_at='2026-11-23T00:00:00+00:00', updated_at='2026-11-23T00:00:00+00:00',
                source='~nouser/x.pdf')
    page = render_memory(item, {}, tmp_path)
    assert 'Body survives' in page
    assert 'Project: [[Chronicle/p/p|p]]' in page
    assert 'Source: `~nouser/x.pdf`\n' in page
    assert 'file://' not in page


@pytest.mark.parametrize('control', [
    *(chr(value) for value in range(0x80, 0xa0)), '\u200e', '\u200f',
    *(chr(value) for value in range(0x202a, 0x202f)),
    *(chr(value) for value in range(0x2066, 0x206a)),
])
def test_c1_and_bidi_controls_are_inert_in_sources_and_stripped_from_labels(tmp_path, control):
    from chronicle.vault.render import _markdown_label, _source_link

    source = str(tmp_path / f'report{control}.pdf')
    assert _source_link(source, tmp_path) == f'`{source.replace(control, " ")}`'
    assert paths.wikilink(f'a{control}b', f'x{control}y') == '[[ab|xy]]'
    assert paths.wikilink('note', control) == '[[note|note]]'
    assert _markdown_label(f'x{control}y') == 'xy'


def test_memory_filename_and_link_agree_after_stripping_format_controls(tmp_path):
    content = 'a\u2066b\u200ec'
    stem = paths.memory_stem('note', content, '12345678-abcd')
    page = paths.memory_file(tmp_path, 'p', stem)
    target = page.relative_to(tmp_path).with_suffix('').as_posix()
    link = paths.wikilink(target, content)
    assert stem == 'note-a-b-c-12345678'
    assert page.stem == stem
    assert link == f'[[Chronicle/p/memories/{stem}|abc]]'
    assert not any(char in value for char in ('\u2066', '\u200e')
                   for value in (stem, page.name, link))
