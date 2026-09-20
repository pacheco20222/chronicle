from pathlib import Path

import pytest

from mnemo import registry


@pytest.fixture
def isolated_registry(tmp_path, monkeypatch):
    path = tmp_path / "projects.json"
    monkeypatch.setenv("MNEMO_REGISTRY_PATH", str(path))
    return path


def test_lookup_returns_none_when_file_missing(isolated_registry):
    assert registry.lookup(Path("/some/never/registered/folder")) is None


def test_register_then_lookup_returns_project(isolated_registry):
    folder = Path("/Users/test/myrepo")
    registry.register(folder, "myproject")
    assert registry.lookup(folder) == "myproject"


def test_register_creates_parent_directory(tmp_path, monkeypatch):
    nested = tmp_path / "nested" / "dir" / "projects.json"
    monkeypatch.setenv("MNEMO_REGISTRY_PATH", str(nested))
    registry.register(Path("/a/b"), "proj")
    assert nested.exists()


def test_reregistering_same_path_overwrites(isolated_registry):
    folder = Path("/Users/test/myrepo")
    registry.register(folder, "first-name")
    registry.register(folder, "second-name")
    assert registry.lookup(folder) == "second-name"


def test_two_different_paths_coexist(isolated_registry):
    folder_a = Path("/Users/test/repo-a")
    folder_b = Path("/Users/test/repo-b")
    registry.register(folder_a, "project-a")
    registry.register(folder_b, "project-b")
    assert registry.lookup(folder_a) == "project-a"
    assert registry.lookup(folder_b) == "project-b"


def test_lookup_uses_resolved_absolute_path(isolated_registry, tmp_path):
    real_dir = tmp_path / "realdir"
    real_dir.mkdir()
    registry.register(real_dir, "resolved-project")
    assert registry.lookup(Path(str(real_dir) + "/.")) == "resolved-project"


def test_load_raises_registry_error_on_corrupt_json(isolated_registry):
    isolated_registry.write_text("{not valid json")
    with pytest.raises(registry.RegistryError):
        registry.lookup(Path("/some/folder"))


def _git(cwd, *args):
    import subprocess
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_lookup_resolves_git_worktree_to_main_repo_project(tmp_path, monkeypatch):
    monkeypatch.setenv("MNEMO_REGISTRY_PATH", str(tmp_path / "projects.json"))
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-q")
    _git(main, "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "x")
    wt = tmp_path / "wt"
    _git(main, "worktree", "add", "-q", str(wt), "-b", "feat")
    registry.register(main, "main-project")
    assert registry.lookup(wt) == "main-project"


def test_lookup_worktree_own_registration_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("MNEMO_REGISTRY_PATH", str(tmp_path / "projects.json"))
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-q")
    _git(main, "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "x")
    wt = tmp_path / "wt"
    _git(main, "worktree", "add", "-q", str(wt), "-b", "feat")
    registry.register(main, "main-project")
    registry.register(wt, "wt-project")
    assert registry.lookup(wt) == "wt-project"


def test_lookup_non_git_dir_unregistered_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("MNEMO_REGISTRY_PATH", str(tmp_path / "projects.json"))
    d = tmp_path / "plain"
    d.mkdir()
    assert registry.lookup(d) is None


def test_register_refuses_home_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("MNEMO_REGISTRY_PATH", str(tmp_path / "projects.json"))
    with pytest.raises(ValueError):
        registry.register(Path.home(), "oops")
    assert not (tmp_path / "projects.json").exists()
