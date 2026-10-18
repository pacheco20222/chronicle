import os
import subprocess
import sys

import pytest

from chronicle import cli, update_cli

pytestmark = pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="needs git",
)


@pytest.fixture(autouse=True)
def git_identity(monkeypatch):
    for key, value in {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
        "GIT_CONFIG_GLOBAL": os.devnull,
    }.items():
        monkeypatch.setenv(key, value)


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def commit_file(repo, name, content, message):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", message)


@pytest.fixture
def repos(tmp_path):
    """An upstream repo and a clone of it, both on main at version 1.0.0."""
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    git(upstream, "init", "-q", "-b", "main")
    commit_file(upstream, "pyproject.toml", 'version = "1.0.0"\n', "v1")
    commit_file(upstream, "dashboard/dist/index.html", "built", "dist")
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(upstream), str(clone))
    return upstream, clone


@pytest.fixture
def side_effects(monkeypatch):
    calls = []
    monkeypatch.setattr(update_cli, "_sync_dependencies", lambda repo: calls.append("deps"))
    monkeypatch.setattr(update_cli, "_build_dashboard", lambda repo: calls.append("dashboard"))
    return calls


def test_already_up_to_date(repos, side_effects, capsys):
    _, clone = repos

    update_cli.update(clone)

    assert "already up to date (version 1.0.0)" in capsys.readouterr().out
    assert side_effects == []


def test_fast_forwards_main_and_reports_versions(repos, side_effects, capsys):
    upstream, clone = repos
    commit_file(upstream, "pyproject.toml", 'version = "1.1.0"\n', "v1.1")

    update_cli.update(clone)

    assert git(clone, "rev-parse", "HEAD") == git(upstream, "rev-parse", "HEAD")
    assert "Updated Chronicle 1.0.0 -> 1.1.0" in capsys.readouterr().out
    assert side_effects == ["deps"]


def test_switches_to_main_from_another_branch(repos, side_effects):
    upstream, clone = repos
    git(clone, "switch", "-q", "-c", "dev")
    commit_file(upstream, "README.md", "new", "docs")

    update_cli.update(clone)

    assert git(clone, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert git(clone, "rev-parse", "HEAD") == git(upstream, "rev-parse", "HEAD")
    assert side_effects == []


def test_rebuilds_dashboard_only_when_it_changed(repos, side_effects):
    upstream, clone = repos
    commit_file(upstream, "dashboard/src/App.tsx", "x", "ui")

    update_cli.update(clone)

    assert side_effects == ["dashboard"]


def test_refuses_with_uncommitted_changes(repos, side_effects):
    upstream, clone = repos
    commit_file(upstream, "README.md", "new", "docs")
    (clone / "pyproject.toml").write_text("edited", encoding="utf-8")

    with pytest.raises(update_cli.UpdateError, match="uncommitted changes"):
        update_cli.update(clone)


def test_refuses_when_local_main_diverged(repos, side_effects):
    upstream, clone = repos
    commit_file(upstream, "README.md", "upstream", "upstream change")
    commit_file(clone, "NOTES.md", "local", "local change")

    with pytest.raises(update_cli.UpdateError, match="can't be fast-forwarded"):
        update_cli.update(clone)


def test_explains_plugin_installs_that_are_not_git_clones(tmp_path):
    (tmp_path / "pyproject.toml").write_text('version = "1.0.0"\n', encoding="utf-8")

    with pytest.raises(update_cli.UpdateError, match="plugin"):
        update_cli.update(tmp_path)


def test_cli_dispatches_update(monkeypatch):
    seen = []
    monkeypatch.setattr(update_cli, "main", lambda argv: seen.append(argv))
    monkeypatch.setattr(cli.sys, "argv", ["chronicle", "update"])

    cli.main()

    assert seen == [[]]


def test_update_path_loads_no_third_party_modules():
    # On Windows, a dependency's compiled module that this process has loaded
    # can't be replaced by the `uv sync` it starts.
    code = (
        "import sys, chronicle.cli, chronicle.console, chronicle.update_cli\n"
        "print([m for m, v in sys.modules.items() "
        "if 'site-packages' in (getattr(v, '__file__', None) or '') "
        "and m.split('.')[0] not in {'_virtualenv', 'pywin32_bootstrap', '_distutils_hack'}])"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)

    assert result.stdout.strip() == "[]"
