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
