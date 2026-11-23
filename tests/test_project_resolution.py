import subprocess
from pathlib import Path

import pytest

from chronicle import registry
from chronicle.project_resolution import (
    ProjectNotFoundError,
    Resolution,
    resolve,
    take_registration_notice,
)
from conftest import git_repo


@pytest.fixture(autouse=True)
def resolution_environment(isolate_server_runtime, monkeypatch):
    monkeypatch.delenv("CHRONICLE_PROJECT", raising=False)


def test_env_var_wins_and_registers_nothing(tmp_path, monkeypatch):
    repo = git_repo(tmp_path / "dolphin")
    monkeypatch.setenv("CHRONICLE_PROJECT", "  pinned  ")
    assert resolve(repo) == Resolution("pinned", False)
    assert registry.list_projects() == {}
    assert take_registration_notice() is None


def test_git_repo_is_registered_under_its_folder_name(tmp_path):
    repo = git_repo(tmp_path / "dolphin")
    assert resolve(repo) == Resolution("dolphin", True)
    assert registry.list_projects() == {"dolphin": [str(repo.resolve())]}
    assert take_registration_notice() == (
        f"Registered {repo.resolve()} as Chronicle project 'dolphin' (git repo, automatic)."
    )
    assert take_registration_notice() is None


def test_subfolder_registers_the_repo_root(tmp_path):
    repo = git_repo(tmp_path / "dolphin")
    (repo / "src").mkdir()
    assert resolve(repo / "src").project == "dolphin"
    assert registry.list_projects() == {"dolphin": [str(repo.resolve())]}


def test_already_registered_repo_is_not_reregistered(tmp_path):
    repo = git_repo(tmp_path / "dolphin")
    resolve(repo)
    take_registration_notice()
    assert resolve(repo) == Resolution("dolphin", False)
    assert take_registration_notice() is None


def test_existing_registration_wins_over_folder_name(tmp_path):
    repo = git_repo(tmp_path / "dolphin")
    registry.register(repo, "custom-name")
    assert resolve(repo) == Resolution("custom-name", False)
    assert take_registration_notice() is None


def test_name_used_by_another_path_is_refused(tmp_path):
    first = git_repo(tmp_path / "a" / "api")
    registry.register(first, "api")
    other = git_repo(tmp_path / "b" / "api")
    with pytest.raises(ProjectNotFoundError, match="already used by") as error:
        resolve(other)
    assert str(first.resolve()) in str(error.value)
    assert "memory_register_project" in str(error.value)
    assert registry.list_projects() == {"api": [str(first.resolve())]}
    assert take_registration_notice() is None


def test_plain_folder_asks_the_user(tmp_path):
    with pytest.raises(ProjectNotFoundError) as error:
        resolve(tmp_path)
    assert "ask the user" in str(error.value)
    assert "memory_register_project" in str(error.value)
    assert registry.list_projects() == {}


def test_home_dotfiles_repo_is_not_registered(tmp_path, monkeypatch):
    home = git_repo(tmp_path / "home")
    monkeypatch.setattr(Path, "home", lambda: home)
    with pytest.raises(ProjectNotFoundError):
        resolve(home)
    assert registry.list_projects() == {}


def test_missing_git_counts_as_plain_folder(tmp_path, monkeypatch):
    repo = git_repo(tmp_path / "dolphin")

    def missing_git(*args, **kwargs):
        raise OSError("no git")

    monkeypatch.setattr(registry.subprocess, "run", missing_git)
    with pytest.raises(ProjectNotFoundError):
        resolve(repo)
    assert registry.list_projects() == {}


def test_no_folder_client_gets_scope_path_guidance():
    with pytest.raises(ProjectNotFoundError) as error:
        resolve(Path("/"))
    assert "memory_list_scopes" in str(error.value)
    assert "scope_path" in str(error.value)


def test_filesystem_root_git_repo_is_not_registered(monkeypatch):
    monkeypatch.setattr(registry, "main_worktree", lambda cwd: Path("/"))
    with pytest.raises(ProjectNotFoundError):
        resolve(Path("/"))
    assert registry.list_projects() == {}


def test_worktree_resolves_to_the_main_repo(tmp_path):
    repo = git_repo(tmp_path / "dolphin")
    for args in (
        ["config", "user.name", "Chronicle Test"],
        ["config", "user.email", "test@example.com"],
        ["commit", "-q", "--allow-empty", "-m", "Initial commit"],
        ["worktree", "add", str(tmp_path / "wt"), "-b", "wt"],
    ):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    assert resolve(tmp_path / "wt").project == "dolphin"
    assert registry.list_projects() == {"dolphin": [str(repo.resolve())]}


def test_corrupt_registry_preserves_error_guidance(tmp_path):
    path = tmp_path / "projects.json"
    path.write_text("{not valid json")
    with pytest.raises(ProjectNotFoundError, match="registry couldn't be read") as error:
        resolve(tmp_path)
    assert isinstance(error.value, RuntimeError)
    assert isinstance(error.value.__cause__, registry.RegistryError)
    assert path.read_text() == "{not valid json"


def test_pending_notice_survives_a_lookup_until_consumed(tmp_path):
    repo = git_repo(tmp_path / "dolphin")
    resolve(repo)
    assert resolve(repo) == Resolution("dolphin", False)
    assert "dolphin" in take_registration_notice()


def test_last_registration_replaces_pending_notice(tmp_path):
    resolve(git_repo(tmp_path / "dolphin"))
    resolve(git_repo(tmp_path / "orca"))
    assert "'orca'" in take_registration_notice()
    assert take_registration_notice() is None
