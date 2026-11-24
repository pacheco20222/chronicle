"""Regression coverage for Obsidian naming and final review fixes."""
import re
from urllib.parse import unquote

import pytest

from chronicle.vault import paths, settings
from chronicle.vault.mirror import VaultMirror
from chronicle.vault.render import _source_link


@pytest.fixture
def mirrored(service, tmp_path):
    vault = settings.set_vault_path(tmp_path / 'vault')
    mirror = VaultMirror(service)
    service.observers.append(mirror.on_memories_changed)
    return vault, mirror


def assert_links_resolve(vault):
    for page in vault.rglob('*.md'):
        for target in re.findall(r'\[\[([^|\]]+)\|', page.read_text()):
            assert not any(char in target for char in '#^[]|')
            assert (vault / (target + '.md')).is_file(), (page, target)


@pytest.mark.parametrize('character', ['#', '^'])
def test_anchor_characters_removed_from_names_and_link_targets(character):
    assert paths.safe_name(f'a{character}b', 80) == 'ab'
    assert paths.memory_stem(f'no{character}te', f'Ti{character}tle', '12345678') == 'note-Title-12345678'
    assert paths.wikilink(f'Notes/C{character}', f'C{character}') == f'[[Notes/C|C{character}]]'


def test_hash_project_folder_gets_suffix():
    assert paths.project_folder_name('c#').startswith('c-')
    assert len(paths.project_folder_name('c#')) == 10


@pytest.mark.parametrize('prefix', ['# ', '######\t', '  ### '])
def test_heading_markers_removed_before_title_bounding(prefix):
    assert paths.memory_title('\n' + prefix + 'Title\nbody') == 'Title'
    assert paths.memory_title(prefix + 'x' * 100) == 'x' * 80
    assert paths.memory_title('####### Title') == '####### Title'
    assert paths.memory_title('#Title') == '#Title'


@pytest.mark.parametrize('character', list('#^[]|'))
def test_special_vault_sources_use_encoded_markdown_links(tmp_path, character):
    source = tmp_path / 'Notes' / f'C{character}(x).md'
    source.parent.mkdir()
    source.write_text('Note')
    link = _source_link(str(source), tmp_path)
    assert link.startswith('[C') and not link.startswith('[[')
    label, destination = link[1:-1].rsplit('](', 1)
    assert unquote(destination) == f'Notes/C{character}(x).md'
    assert not any(char in destination for char in '#^[]|()')
    assert label == f'C{"\\" if character in "[]" else ""}{character}(x).md'
    source.unlink()
    assert _source_link(str(source), tmp_path) == link + ' (file not found)'
    assert _source_link(str(source.with_suffix('.sh')), tmp_path).startswith('`')


def test_special_character_in_source_folder_also_uses_markdown(tmp_path):
    source = tmp_path / 'C#' / 'note.pdf'
    source.parent.mkdir()
    source.write_text('Note')
    assert _source_link(str(source), tmp_path) == '[note.pdf](C%23/note.pdf)'


def test_legacy_anchor_stem_replaced_and_pruned(service, mirrored):
    vault, mirror = mirrored
    settings.add_project('c#')
    memory_id = service.add_memory([], '# Title^', 'c#', 'note')
    folder = paths.project_dir(vault, 'c#')
    original = next((folder / 'memories').glob('*.md'))
    legacy = original.with_name(f'note-#-Title^-{memory_id[:8]}.md')
    original.rename(legacy)
    user = legacy.with_name('user-#-page.md')
    user.write_text('Keep me')
    result = mirror.sync_project('c#')
    assert result.error is None
    assert not legacy.exists()
    clean = next(path for path in (folder / 'memories').glob('*.md') if path != user)
    assert clean.stem == f'note-Title-{memory_id[:8]}'
    assert user.read_text() == 'Keep me'
    assert_links_resolve(vault)


def test_heading_cleanup_preserves_existing_safe_stem(service, mirrored):
    vault, mirror = mirrored
    settings.add_project('p')
    memory_id = service.add_memory([], '# Title', 'p', 'note')
    original = next((paths.project_dir(vault, 'p') / 'memories').glob('*.md'))
    stable = original.with_name(f'note-old-title-{memory_id[:8]}.md')
    original.rename(stable)
    assert mirror.sync_project('p').error is None
    assert stable.exists()
    log = (paths.project_dir(vault, 'p') / 'log.md').read_text()
    assert 'created | Title\n' in log and '|Title]]' in log
    assert_links_resolve(vault)


def test_case_variants_have_distinct_folders_and_independent_sync(service, mirrored):
    vault, mirror = mirrored
    for project in ('Foo', 'foo'):
        settings.add_project(project)
        service.add_memory([], 'Title', project, 'note')
        assert mirror.sync_project(project).error is None
    upper, lower = (paths.project_dir(vault, name) for name in ('Foo', 'foo'))
    assert upper.name.casefold() != lower.name.casefold()
    before = {path: path.read_bytes() for path in lower.rglob('*.md')}
    assert mirror.sync_project('Foo').error is None
    assert {path: path.read_bytes() for path in lower.rglob('*.md')} == before
    assert_links_resolve(vault)


@pytest.mark.parametrize('foreign', [False, True])
def test_legacy_uppercase_folder_prunes_only_owned_marked_files(service, mirrored, foreign):
    from chronicle.vault.render import _frontmatter

    vault, mirror = mirrored
    settings.add_project('Foo')
    service.add_memory([], 'Title', 'Foo', 'note')
    legacy = vault / 'Chronicle' / 'Foo'
    legacy.mkdir(exist_ok=True)
    owned = legacy / 'old.md'
    owned.write_text(_frontmatter(project='Foo') + 'Old')
    user = legacy / 'user.md'
    user.write_text('Keep me')
    other = legacy / 'other.md'
    if foreign:
        other.write_text(_frontmatter(project='foo') + 'Other')
    assert mirror.sync_project('Foo').error is None
    assert not owned.exists()
    assert user.read_text() == 'Keep me'
    if foreign:
        assert other.read_text() == _frontmatter(project='foo') + 'Other'


def test_live_refresh_only_resolves_paths_for_affected_memories(service, mirrored, monkeypatch):
    from chronicle.vault import mirror as module

    vault, mirror = mirrored
    settings.add_project('p')
    for index in range(12):
        service.add_memory([], f'Note {index}', 'p', 'note')
    resolved = []
    original = module.memory_file

    def counted(*args):
        resolved.append(args)
        return original(*args)

    monkeypatch.setattr(module, 'memory_file', counted)
    memory_id = service.add_memory([], 'New', 'p', 'note')
    assert len(resolved) == 1
    assert list((paths.project_dir(vault, 'p') / 'memories').glob(f'*-{memory_id[:8]}.md'))
