import json
from dataclasses import FrozenInstanceError

import pytest

from chronicle.vault import paths


def memory(**changes):
    item = dict(id='12345678-abcd', project='p', type='note', status='active',
                content='\n  Title  \nBody **verbatim**\n', created_at='2026-11-20T12:00:00+00:00',
                updated_at='2026-11-22T12:00:00+00:00', invalid_at=None,
                confidence=None, source=None, source_kind=None, supersedes=None,
                relations=[])
    return item | changes


def link_targets(items):
    from chronicle.vault.render import LinkTarget

    return {item['id']: LinkTarget(item['project'],
                                  paths.memory_stem(item['type'], item['content'], item['id']),
                                  paths.memory_title(item['content'])) for item in items}


def frontmatter(page):
    block = page.split('---\n', 2)[1]
    result = {}
    for line in block.splitlines():
        key, value = line.split(': ', 1)
        result[key] = json.loads(value)
    return result


def test_memory_page_frontmatter_parses_with_hostile_values(tmp_path):
    from chronicle.vault.render import render_memory

    item = memory(project='p"q\n---', source='C:\\a "b": c', confidence=0.9)
    page = render_memory(item, {}, tmp_path)
    properties = frontmatter(page)
    assert properties == dict(chronicle_id=item['id'], project=item['project'],
                              type='note', status='active', created=item['created_at'],
                              updated=item['updated_at'], source=item['source'],
                              confidence=0.9, generated_by='chronicle')
    assert item['content'] in page


def test_supersede_and_relation_links_use_full_paths(tmp_path):
    from chronicle.vault.render import LinkTarget, render_memory

    links = {'old': LinkTarget('a/b', 'note-old-aaaaaaaa', 'Old'),
             'new': LinkTarget('q', 'note-new-bbbbbbbb', 'New')}
    item = memory(supersedes='old', relations=[{'type': 'supports', 'target': 'new'}],
                  _inbound=[{'type': 'supersedes', 'source': 'new'},
                            {'type': 'supports', 'source': 'old'}])
    page = render_memory(item, links, tmp_path)
    old = f'[[Chronicle/{paths.project_folder_name("a/b")}/memories/note-old-aaaaaaaa|Old]]'
    new = '[[Chronicle/q/memories/note-new-bbbbbbbb|New]]'
    for line in ['Project: [[Chronicle/p/p|p]]', f'Replaces: {old}',
                 f'Replaced by: {new}', f'supports: {new}', f'supports (from): {old}']:
        assert line in page
    with pytest.raises(FrozenInstanceError):
        links['old'].title = 'changed'


def test_unmirrored_link_target_renders_plain_text_without_content(tmp_path):
    from chronicle.vault.render import LinkTarget, render_memory

    page = render_memory(memory(supersedes='secret'),
                         {'secret': LinkTarget('secret_proj', None, 'SECRET CONTENT')}, tmp_path)
    assert 'Replaces: (in project secret_proj, not mirrored)' in page
    assert 'SECRET CONTENT' not in page


@pytest.mark.parametrize('status, banner', [('superseded', 'Replaced by [[Chronicle/q/memories/new|New]]'),
                                            ('wrong', 'Marked wrong'), ('deleted', 'Retracted')])
def test_banners_for_superseded_wrong_retracted(tmp_path, status, banner):
    from chronicle.vault.render import LinkTarget, render_memory

    page = render_memory(memory(status=status, _inbound=[{'type': 'supersedes', 'source': 'new'}]),
                         {'new': LinkTarget('q', 'new', 'New')}, tmp_path)
    assert f'> {banner}\n' in page


@pytest.mark.parametrize('extension', ['.md', '.pdf'])
def test_source_in_vault_is_wikilink_outside_is_file_url_missing_is_flagged(tmp_path, extension):
    from chronicle.vault.render import render_memory

    vault = tmp_path / 'vault'
    vault.mkdir()
    source = vault / ('A note' + extension)
    source.write_text('source')
    target = 'A note' if extension == '.md' else source.name
    page = render_memory(memory(source=str(source)), {}, vault)
    assert f'Source: [[{target}|{source.name}]]' in page
    outside = tmp_path / 'outside #.pdf'
    outside.write_text('source')
    page = render_memory(memory(source=str(outside)), {}, vault)
    assert f'Source: [{outside.name}]({outside.as_uri()})' in page
    assert '(file not found)' not in page
    outside.unlink()
    assert '(file not found)' in render_memory(memory(source=str(outside)), {}, vault)
    source.unlink()
    assert '(file not found)' in render_memory(memory(source=str(source)), {}, vault)
    url = 'https://example.com/a'
    assert f'Source: [{url}]({url})' in render_memory(memory(source=url), {}, vault)


def test_log_is_newest_first_and_grep_friendly():
    from chronicle.vault.render import render_log

    items = [memory(status='superseded', invalid_at='2026-11-21T00:00:00+00:00'),
             memory(id='bbbbbbbb', status='wrong', invalid_at='2026-11-23T00:00:00+00:00'),
             memory(id='cccccccc', status='deleted')]
    page = render_log('p', items, link_targets(items))
    headings = [line for line in page.splitlines() if line.startswith('## [')]
    assert headings[:3] == ['## [2026-11-23] marked wrong | Title',
                            '## [2026-11-22] retracted | Title',
                            '## [2026-11-21] superseded | Title']
    assert headings.count('## [2026-11-20] created | Title') == 3
    assert '[[Chronicle/p/memories/note-Title-12345678|Title]]' in page
    assert frontmatter(page)['generated_by'] == 'chronicle'


def test_project_page_links_log_files_and_recent_memories(tmp_path):
    from chronicle.vault.render import render_project

    page = render_project('a/b', 'Overview **verbatim**', [memory(project='a/b')], tmp_path,
                          link_targets([memory(project='a/b')]))
    folder = paths.project_folder_name('a/b')
    assert f'[[Chronicle/{folder}/log|log]]' in page
    assert f'[[Chronicle/{folder}/files|files]]' in page
    assert f'[[Chronicle/{folder}/memories/note-Title-12345678|Title]]' in page
    assert 'Overview **verbatim**' in page
    assert 'note: 1' in page and 'active: 1' in page
    assert frontmatter(page)['project'] == 'a/b'


def test_renderers_are_deterministic_and_do_not_mutate_inputs(tmp_path):
    from copy import deepcopy
    from chronicle.vault.render import render_index, render_log, render_memory, render_project

    item = memory()
    before = deepcopy(item)
    for render in [lambda: render_memory(item, {}, tmp_path),
                   lambda: render_project('p', None, [item], tmp_path, link_targets([item])),
                   lambda: render_log('p', [item], link_targets([item])),
                   lambda: render_index([('a/b', 'Summary')])]:
        assert render() == render()
        assert frontmatter(render())['generated_by'] == 'chronicle'
    assert item == before
    page = render_index([('a/b', 'Summary')])
    folder = paths.project_folder_name('a/b')
    assert f'[[Chronicle/{folder}/{folder}|a/b]]' in page
    assert 'Summary' in page


def test_recent_memories_are_bounded_per_type_and_newest_first(tmp_path):
    from chronicle.vault.render import render_project

    items = [memory(id=f'{number:08d}', content=f'Title {number}',
                    created_at=f'2026-11-{number + 1:02d}T00:00:00+00:00') for number in range(7)]
    items.append(memory(id='decision', type='decision', content='Decision'))
    page = render_project('p', None, items, tmp_path, link_targets(items))
    assert 'Title 0' not in page and 'Title 1' not in page
    assert page.index('|Title 6]]') < page.index('|Title 2]]')
    assert '|Decision]]' in page
    assert 'note: 7' in page
    assert page == render_project('p', None, list(reversed(items)), tmp_path, link_targets(items))


def test_log_compares_actual_instants_and_has_stable_ties():
    from chronicle.vault.render import render_log

    early = memory(id='aaaaaaaa', content='Early', created_at='2026-11-21T01:00:00+02:00')
    late = memory(id='bbbbbbbb', content='Late', created_at='2026-11-20T23:30:00+00:00')
    page = render_log('p', [early, late], link_targets([early, late]))
    assert page.index('| Late') < page.index('| Early')
    assert page == render_log('p', [late, early], link_targets([early, late]))


def test_supersedes_relation_is_not_duplicated(tmp_path):
    from chronicle.vault.render import LinkTarget, render_memory

    item = memory(supersedes='old', relations=[{'type': 'supersedes', 'target': 'old'}])
    page = render_memory(item, {'old': LinkTarget('p', 'old', 'Old')}, tmp_path)
    assert page.count('Replaces: ') == 1
    assert 'supersedes:' not in page


def test_aliases_and_log_titles_use_shared_trimmed_eighty_character_title(tmp_path):
    from chronicle.vault.render import render_log, render_project

    item = memory(content=' \n  ' + 'x' * 100 + '  \nbody')
    title = 'x' * 80
    assert f'created | {title}\n' in render_log('p', [item], link_targets([item]))
    assert f'|{title}]]' in render_project('p', None, [item], tmp_path, link_targets([item]))


def test_empty_project_log_and_index_have_generated_marker(tmp_path):
    from chronicle.vault.render import render_index, render_log, render_project

    for page in [render_project('p', None, [], tmp_path, {}), render_log('p', [], {}), render_index([])]:
        assert frontmatter(page)['generated_by'] == 'chronicle'


def test_index_sorts_projects_and_keeps_summaries_on_one_line():
    from chronicle.vault.render import render_index

    projects = [('z', 'first\nsecond'), ('a', 'Summary')]
    page = render_index(projects)
    assert page.index('Chronicle/a/a') < page.index('Chronicle/z/z')
    assert 'first second' in page
    assert page == render_index(list(reversed(projects)))


def test_project_and_log_keep_supplied_target_after_content_edit(tmp_path):
    from chronicle.vault.render import LinkTarget, render_log, render_project

    item = memory(content='Changed first line\nEdited body')
    links = {item['id']: LinkTarget('p', 'note-original-12345678', 'Original title')}
    for page in [render_project('p', None, [item], tmp_path, links),
                 render_log('p', [item], links)]:
        assert '[[Chronicle/p/memories/note-original-12345678|Original title]]' in page
        assert 'Changed' not in page
    assert 'created | Original title\n' in render_log('p', [item], links)


@pytest.mark.parametrize('page_type', ['project', 'log'])
def test_project_and_log_fail_visibly_for_missing_target(tmp_path, page_type):
    from chronicle.vault.render import render_log, render_project

    item = memory()
    with pytest.raises(KeyError) as caught:
        if page_type == 'project':
            render_project('p', None, [item], tmp_path, {})
        else:
            render_log('p', [item], {})
    assert caught.value.args == (item['id'],)


def test_external_source_parentheses_are_encoded(tmp_path, monkeypatch):
    from chronicle.vault.render import render_memory

    source = tmp_path / 'report (1).pdf'
    source.write_text('source')
    uri = source.as_uri().replace('(', '%28').replace(')', '%29')
    # Emulate pathlib versions that leave parentheses unescaped in file URIs.
    monkeypatch.setattr(type(source), 'as_uri',
                        lambda self: uri.replace('%28', '(').replace('%29', ')'))
    page = render_memory(memory(source=str(source)), {}, tmp_path / 'vault')
    assert f'Source: [report (1).pdf]({uri})' in page


@pytest.mark.parametrize('status', ['active', 'wrong', 'deleted'])
def test_log_heading_dates_use_utc_for_created_and_status_events(status):
    from chronicle.vault.render import render_log

    at = '2026-11-21T01:00:00+02:00'
    item = memory(status=status, created_at=at, invalid_at=at, updated_at=at)
    page = render_log('p', [item], link_targets([item]))
    headings = [line for line in page.splitlines() if line.startswith('## [')]
    assert len(headings) == (1 if status == 'active' else 2)
    assert all(line.startswith('## [2026-11-20]') for line in headings)


@pytest.mark.parametrize('kind', ['traversal', 'outbound_symlink', 'inbound_symlink', 'vault_alias'])
@pytest.mark.parametrize('missing', [False, True])
def test_source_containment_uses_resolved_paths(tmp_path, kind, missing):
    from chronicle.vault.render import render_memory

    vault = tmp_path / 'vault'
    vault.mkdir()
    inside = vault / 'note.pdf'
    outside = tmp_path / 'outside.pdf'
    if not missing:
        inside.write_text('inside')
        outside.write_text('outside')
    source = vault / '..' / outside.name
    if kind == 'outbound_symlink':
        source = vault / 'linked.pdf'
        source.symlink_to(outside)
    elif kind == 'inbound_symlink':
        source = tmp_path / 'linked.pdf'
        source.symlink_to(inside)
    elif kind == 'vault_alias':
        alias = tmp_path / 'alias'
        alias.symlink_to(vault, target_is_directory=True)
        vault, source = alias, inside
    page = render_memory(memory(source=str(source)), {}, vault)
    expected = '[[note.pdf|note.pdf]]' if kind in {'inbound_symlink', 'vault_alias'} else f'[{outside.name}]({outside.as_uri()})'
    assert f'Source: {expected}' in page
    assert ('(file not found)' in page) == missing


@pytest.mark.parametrize('inside', [False, True])
@pytest.mark.parametrize('suffix', ['.app', '.command', '.sh', '.exe', '.bat', '.ps1', '.jar', '', '.html'])
def test_unsafe_source_extensions_are_inert(tmp_path, inside, suffix):
    from chronicle.vault.render import render_memory

    vault = tmp_path / 'vault'
    vault.mkdir()
    source = (vault if inside else tmp_path) / ('run`me' + suffix)
    source.write_text('untrusted')
    page = render_memory(memory(source=str(source)), {}, vault)
    assert f'Source: `{str(source).replace("`", "")}`\n' in page
    assert 'file://' not in page
    source.unlink()
    assert f'Source: `{str(source).replace("`", "")}` (file not found)' in render_memory(memory(source=str(source)), {}, vault)


@pytest.mark.parametrize('suffix', 'pdf doc docx xls xlsx ppt pptx odt ods odp rtf txt md csv json png jpg jpeg gif webp svg mp3 mp4 mov wav'.split())
def test_document_media_allowlist_is_case_insensitive(tmp_path, suffix):
    from chronicle.vault.render import render_memory

    source = tmp_path / ('document.' + suffix.upper())
    source.write_text('document')
    assert f'Source: [{source.name}]({source.as_uri()})' in render_memory(memory(source=str(source)), {}, tmp_path / 'vault')


@pytest.mark.parametrize('inside', [False, True])
def test_directories_with_document_extensions_are_inert(tmp_path, inside):
    from chronicle.vault.render import render_memory

    vault = tmp_path / 'vault'
    vault.mkdir()
    source = (vault if inside else tmp_path) / 'folder.pdf'
    source.mkdir()
    assert f'Source: `{source}`\n' in render_memory(memory(source=str(source)), {}, vault)


@pytest.mark.parametrize('source', ['javascript:alert(1)', 'file:///tmp/document.pdf', 'ftp://example.com/a.pdf'])
def test_non_http_url_sources_are_inert(tmp_path, source):
    from chronicle.vault.render import render_memory

    assert f'Source: `{source}`\n' in render_memory(memory(source=source), {}, tmp_path)


@pytest.mark.parametrize('suffix, clickable', [('.command', False), ('.PDF', True)])
def test_source_symlink_policy_uses_resolved_extension(tmp_path, suffix, clickable):
    from chronicle.vault.render import render_memory

    vault = tmp_path / 'vault'
    vault.mkdir()
    target = tmp_path / ('target' + suffix)
    target.write_text('target')
    source = vault / 'disguised.pdf'
    source.symlink_to(target)
    page = render_memory(memory(source=str(source)), {}, vault)
    expected = f'[{target.name}]({target.as_uri()})' if clickable else f'`{target}`'
    assert f'Source: {expected}\n' in page


@pytest.mark.parametrize('suffix, clickable', [('.PDF', True), ('.exe', False)])
def test_windows_absolute_sources_on_posix_are_external_without_resolution(tmp_path, monkeypatch, suffix, clickable):
    import os
    from pathlib import Path
    from chronicle.vault.render import render_memory

    if os.name == 'nt':
        pytest.skip('foreign Windows paths require POSIX')
    source = 'C:\\documents\\report' + suffix
    monkeypatch.setattr(Path, 'resolve', lambda *args, **kwargs: pytest.fail('must not resolve foreign source'))
    page = render_memory(memory(source=source), {}, tmp_path)
    expected = f'[report{suffix}](file:///C:/documents/report{suffix})' if clickable else f'`{source}`'
    assert f'Source: {expected} (file not found)' in page


@pytest.mark.parametrize('source', ['x\n\n# H.pdf', 'x\n\n<https://evil>.pdf',
                                    'https://example.com/x\n\n# H', 'a\x00b.pdf',
                                    'https://example.com/end\\'])
def test_hostile_source_strings_are_single_inert_code_spans(tmp_path, source):
    from chronicle.vault.render import _source_link

    if not source.startswith('https:'):
        source = str(tmp_path / source)
    rendered = _source_link(source, tmp_path)
    assert rendered.startswith('`') and rendered.endswith('`')
    assert rendered.count('`') == 2
    assert not any(ord(char) < 0x20 or ord(char) == 0x7f or char in '\u2028\u2029' for char in rendered)
    assert '\n# H' not in rendered and '\n<https://evil>' not in rendered


@pytest.mark.parametrize('control', [chr(value) for value in range(32)] + ['\x7f', '\u2028', '\u2029'])
def test_all_source_control_characters_are_inert(tmp_path, control):
    from chronicle.vault.render import _source_link

    rendered = _source_link(f'https://example.com/a{control}b.pdf', tmp_path)
    assert rendered.startswith('`') and rendered.endswith('`')
    assert control not in rendered


def test_link_labels_and_http_destinations_escape_markup(tmp_path):
    from chronicle.vault.render import _markdown_label, _source_link

    assert _markdown_label('<title>`[x]') == '\\<title\\>\\`\\[x\\]'
    url = 'https://example.com/a <tag>(1)`'
    assert _source_link(url, tmp_path) == (
        '[https://example.com/a \\<tag\\>(1)\\`]'
        '(https://example.com/a%20%3Ctag%3E%281%29%60)'
    )


def test_external_file_label_escapes_angle_brackets_and_backticks(tmp_path):
    from chronicle.vault.render import _source_link

    source = tmp_path / '<title>`file.pdf'
    assert _source_link(str(source), tmp_path / 'vault').startswith(
        '[\\<title\\>\\`file.pdf]('
    )


def test_relative_source_is_inert_independent_of_cwd(tmp_path, monkeypatch):
    from chronicle.vault.render import _source_link

    other = tmp_path / 'other'
    other.mkdir()
    monkeypatch.chdir(tmp_path)
    first = _source_link('notes/report.pdf', tmp_path)
    monkeypatch.chdir(other)
    assert first == _source_link('notes/report.pdf', tmp_path) == '`notes/report.pdf`'


@pytest.mark.parametrize('error', [ValueError('bad path'), OSError('unavailable path')])
def test_source_path_errors_render_inert(tmp_path, monkeypatch, error):
    from pathlib import Path
    from chronicle.vault.render import _source_link

    source = str(tmp_path / 'report.pdf')
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(Path, 'resolve', fail)
    assert _source_link(source, tmp_path) == f'`{source}`'


def test_nul_source_does_not_abort_memory_page(tmp_path):
    from chronicle.vault.render import render_memory

    item = memory(source='a\x00b.pdf')
    page = render_memory(item, {}, tmp_path)
    assert item['content'] in page
    assert 'Project: [[Chronicle/p/p|p]]' in page
    assert 'Source: `a b.pdf`\n' in page
    assert frontmatter(page)['source'] == item['source']


def test_symlink_to_control_character_filename_is_inert(tmp_path):
    from chronicle.vault.render import _source_link

    target = tmp_path / 'report\n\n# H.pdf'
    target.write_text('document')
    source = tmp_path / 'alias.pdf'
    source.symlink_to(target)
    rendered = _source_link(str(source), tmp_path / 'vault')
    assert rendered.startswith('`') and rendered.endswith('`')
    assert '\n' not in rendered


def test_expanded_home_source_remains_a_document_link(tmp_path, monkeypatch):
    from chronicle.vault.render import _source_link

    monkeypatch.setenv('HOME', str(tmp_path))
    source = tmp_path / 'report.pdf'
    source.write_text('document')
    assert _source_link('~/report.pdf', tmp_path / 'vault') == f'[report.pdf]({source.as_uri()})'


def test_project_headings_share_markdown_escaping(tmp_path):
    from chronicle.vault.catalog import render_files
    from chronicle.vault.render import render_index, render_log, render_project

    project = '<tag>`[x]\n'
    heading = r'\<tag\>\`\[x\]'
    for text in (render_project(project, None, [], tmp_path, {}),
                 render_log(project, [], {}), render_files(project, [], False)):
        assert f'# {heading}' in text
    assert '<tag>' not in render_index([(project, '')])
