import json
import os
from pathlib import Path

import pytest

from chronicle import config
from chronicle.vault import paths, settings, writer


MARKED = '---\ngenerated_by: "chronicle"\n---\nHello\n'


def test_config_is_isolated():
    assert config.CONFIG_PATH == Path(os.environ["CHRONICLE_CONFIG_PATH"])
    assert config.CONFIG_PATH != Path.home() / ".chronicle" / "config.json"


def test_settings_roundtrip_and_opt_in(tmp_path):
    assert settings.vault_path() is None
    assert settings.vault_projects() == []
    assert settings.similarity_links() is False
    settings.add_project("p")
    assert settings.is_mirrored("p") is False
    vault = settings.set_vault_path(tmp_path / "v")
    assert vault == (tmp_path / "v").resolve()
    assert (vault / "Chronicle").is_dir()
    assert settings.vault_path() == vault
    settings.add_project("p")
    settings.add_project("q")
    assert settings.vault_projects() == ["p", "q"]
    assert settings.is_mirrored("p") is True
    assert settings.is_mirrored("other") is False
    settings.remove_project("p")
    settings.remove_project("missing")
    assert settings.vault_projects() == ["q"]
    assert settings.is_mirrored("p") is False


def test_set_vault_path_refuses_home_and_root(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    alias = tmp_path / "alias"
    alias.symlink_to(home, target_is_directory=True)
    for path in (home, alias, Path(home.anchor)):
        with pytest.raises(ValueError):
            settings.set_vault_path(path)
    assert not (home / "Chronicle").exists()
    assert not config.CONFIG_PATH.exists()


def test_set_vault_path_expands_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert settings.set_vault_path(Path("~/vault")) == tmp_path / "vault"


def test_semantic_setting_survives_vault_writes(tmp_path, monkeypatch):
    monkeypatch.delenv("CHRONICLE_SEMANTIC")
    config.write_config({"other": 42})
    config.set_semantic(True)
    settings.set_vault_path(tmp_path / "vault")
    settings.add_project("p")
    settings.remove_project("missing")
    assert config.semantic_enabled() is True
    config.set_semantic(False)
    assert settings.is_mirrored("p") is True
    assert config.read_config()["other"] == 42


def test_settings_read_fresh_config(tmp_path):
    config.CONFIG_PATH.write_text(json.dumps({
        "vault_path": str(tmp_path), "vault_projects": ["p"],
        "vault_similarity_links": True, "other": 42,
    }))
    assert settings.is_mirrored("p") is True
    assert settings.similarity_links() is True
    config.CONFIG_PATH.write_text('{}')
    assert settings.vault_path() is None
    assert settings.vault_projects() == []
    assert settings.is_mirrored("p") is False
    assert settings.similarity_links() is False


@pytest.mark.parametrize("text", ['{ bad json', '[]', 'null', '42'])
def test_config_helpers_recover_invalid_config(text):
    config.CONFIG_PATH.write_text(text)
    assert config.read_config() == {}
    settings.add_project("p")
    assert config.read_config() == {"vault_projects": ["p"]}


@pytest.mark.parametrize("existing", [False, True])
def test_config_write_is_atomic_and_cleans_temp(tmp_path, monkeypatch, existing):
    if existing:
        config.write_config({"other": 42})
    before = config.CONFIG_PATH.read_bytes() if existing else None
    entries = sorted(tmp_path.iterdir())

    def fail_replace(source, target):
        assert Path(source).parent == config.CONFIG_PATH.parent
        assert Path(target) == config.CONFIG_PATH
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        config.write_config({"semantic": True})
    assert (config.CONFIG_PATH.read_bytes() if existing else None) == before
    assert sorted(tmp_path.iterdir()) == entries


def test_identical_first_lines_get_distinct_stems():
    assert paths.memory_stem("note", "Same line", "aaaaaaaa-1") != paths.memory_stem(
        "note", "Same line", "bbbbbbbb-2"
    )


@pytest.mark.parametrize("text", [
    "../../etc/passwd", "CON", "aux.txt", 'a/b\\c:d*?"<>|',
    "🙂" * 200, "x" * 500, "   \n\n",
])
def test_stem_is_safe_and_bounded(text):
    stem = paths.memory_stem("note", text, "12345678-abcd")
    assert len(stem) <= 80
    assert not any(char in stem for char in '/\\<>:"|?*')
    assert ".." not in stem
    assert stem.endswith("12345678")


def test_stem_uses_first_nonempty_line():
    assert paths.memory_stem("note", "", "12345678-x") == "note-untitled-12345678"
    assert paths.memory_stem("note", " \n First title \nignored", "12345678-x") == "note-First-title-12345678"


@pytest.mark.parametrize("name", ["CON", "prn", "Aux.txt", "NUL", "COM1", "com9", "LPT1", "lpt9"])
def test_safe_name_handles_windows_reserved_names(name):
    base, dot, extension = name.partition(".")
    assert paths.safe_name(name, 80) == base + "_" + dot + extension


def test_safe_name_sanitizes_controls_and_truncation():
    assert paths.safe_name(' a\tb\n c\x00\x7f<>:"/\\|?*.. ', 80) == "ab-c"
    assert paths.safe_name("CONlong", 3) != "CON"
    assert len(paths.safe_name("x" * 500, 80)) == 80
    assert paths.safe_name("...", 80) == "untitled"


def test_project_dir_with_traversal_name_stays_inside(tmp_path):
    root = paths.chronicle_root(tmp_path)
    project = paths.project_dir(tmp_path, "../evil")
    assert project.parent == root
    assert ".." not in project.name
    page = paths.memory_file(tmp_path, "../evil", "note-x-12345678")
    assert page == project / "memories" / "note-x-12345678.md"
    with pytest.raises(ValueError):
        paths.inside_root(tmp_path, tmp_path / "elsewhere.md")


@pytest.mark.parametrize("at_root", [False, True])
def test_inside_root_rejects_symlink_escape(tmp_path, at_root):
    vault = tmp_path / "vault"
    outside = tmp_path / "outside"
    vault.mkdir()
    outside.mkdir()
    root = vault / "Chronicle"
    if at_root:
        root.symlink_to(outside, target_is_directory=True)
    else:
        root.mkdir()
        (root / "p").symlink_to(outside, target_is_directory=True)
    candidate = root / "p" / "note.md"
    with pytest.raises(ValueError):
        paths.inside_root(vault, candidate)
    with pytest.raises(ValueError):
        writer.write_page(vault, candidate, MARKED)
    with pytest.raises(ValueError):
        writer.delete_page(vault, candidate)
    assert list(outside.iterdir()) == []


def test_set_vault_path_rejects_redirected_chronicle(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Chronicle").symlink_to(tmp_path / "outside", target_is_directory=True)
    with pytest.raises(ValueError):
        settings.set_vault_path(vault)
    assert not (tmp_path / "outside").exists()
    assert not config.CONFIG_PATH.exists()


@pytest.mark.parametrize("text, expected", [
    (MARKED, True), ('---\ntitle: "x"\ngenerated_by: "chronicle"\n---\n', True),
    ('user note\ngenerated_by: "chronicle"\n', False),
    ('---\ntitle: "x"\n---\ngenerated_by: "chronicle"\n', False),
    ('---\ngenerated_by: "chronicle"\n', False),
    ('---\ngenerated_by: chronicle\n---\n', False),
    ('---\n  generated_by: "chronicle"\n---\n', False),
])
def test_marker_only_in_leading_frontmatter(tmp_path, text, expected):
    page = tmp_path / "page.md"
    assert writer.is_generated(page) is False
    page.write_text(text)
    assert writer.is_generated(page) is expected


def test_write_page_is_atomic_and_marker_protected(tmp_path, monkeypatch):
    page = paths.memory_file(tmp_path, "p", "note-x-12345678")
    assert writer.write_page(tmp_path, page, MARKED) is True
    assert page.read_text() == MARKED
    page.write_text("User note")
    assert writer.write_page(tmp_path, page, MARKED) is False
    assert page.read_text() == "User note"
    page.write_text(MARKED)
    assert writer.write_page(tmp_path, page, MARKED + "Updated") is True

    def fail_replace(source, target):
        assert Path(source).parent == page.parent
        assert Path(target) == page
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        writer.write_page(tmp_path, page, MARKED)
    assert page.read_text() == MARKED + "Updated"
    page.unlink()
    with pytest.raises(OSError, match="replace failed"):
        writer.write_page(tmp_path, page, MARKED)
    assert list(page.parent.iterdir()) == []


def test_identical_write_does_not_replace(tmp_path, monkeypatch):
    page = paths.memory_file(tmp_path, "p", "note-x-12345678")
    writer.write_page(tmp_path, page, MARKED)
    before = page.stat().st_mtime_ns
    monkeypatch.setattr(os, "replace", lambda *args: pytest.fail("must not rewrite"))
    assert writer.write_page(tmp_path, page, MARKED) is True
    assert page.stat().st_mtime_ns == before


def test_delete_page_only_deletes_marked_files(tmp_path):
    page = paths.memory_file(tmp_path, "p", "note-x-12345678")
    assert writer.delete_page(tmp_path, page) is False
    page.parent.mkdir(parents=True)
    page.write_text("User note")
    assert writer.delete_page(tmp_path, page) is False
    assert page.read_text() == "User note"
    page.write_text(MARKED)
    assert writer.delete_page(tmp_path, page) is True
    assert not page.exists()


def test_wikilink_format():
    assert paths.MARKER == "chronicle"
    assert paths.wikilink("Chronicle/p/memories/note-x-12345678", "x") == "[[Chronicle/p/memories/note-x-12345678|x]]"


def test_writer_rejects_file_symlink_and_parent_traversal(tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text(MARKED)
    root = tmp_path / "Chronicle"
    root.mkdir()
    link = root / "linked.md"
    link.symlink_to(outside)
    for page in (link, root / ".." / "outside.md"):
        with pytest.raises(ValueError):
            writer.write_page(tmp_path, page, MARKED + "changed")
        with pytest.raises(ValueError):
            writer.delete_page(tmp_path, page)
    assert outside.read_text() == MARKED


def test_non_utf8_user_file_is_protected(tmp_path):
    page = tmp_path / "Chronicle" / "user.md"
    page.parent.mkdir()
    page.write_bytes(b"\xffuser note")
    assert writer.is_generated(page) is False
    assert writer.write_page(tmp_path, page, MARKED) is False
    assert writer.delete_page(tmp_path, page) is False
    assert page.read_bytes() == b"\xffuser note"
