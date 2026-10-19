"""`chronicle update`: bring a git clone of chronicle up to date with main.

Deliberately stdlib-only: on Windows a running Python can't have its loaded
compiled dependencies (.pyd files) replaced, and this process is the one
asking uv to sync them.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

BRANCH = "main"
REMOTE = "origin"


class UpdateError(Exception):
    pass


def _say(message: str, **kwargs) -> None:
    # flush, so messages stay in order with the git/uv/npm output around them
    print(message, flush=True, **kwargs)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _run(args: list[str], cwd: Path, **kwargs) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, cwd=cwd, text=True, check=False, **kwargs)
    except OSError as error:
        raise UpdateError(f"could not run `{args[0]}`: {error}") from error


def _git(repo: Path, *args: str) -> str:
    result = _run(["git", *args], repo, capture_output=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise UpdateError(f"`git {' '.join(args)}` failed: {detail}")
    return result.stdout.strip()


def _version(repo: Path) -> str:
    pyproject = repo / "pyproject.toml"
    if not pyproject.is_file():
        return "unknown"
    for line in pyproject.read_text(encoding="utf-8").splitlines():
        if line.startswith("version"):
            return line.split("=", 1)[1].strip().strip("\"'")
    return "unknown"


def _changed(repo: Path, old: str, new: str, *paths: str) -> bool:
    return bool(_git(repo, "diff", "--name-only", old, new, "--", *paths))


def _update_git(repo: Path) -> tuple[str, str]:
    if not (repo / ".git").exists():
        raise UpdateError(
            f"{repo} is not a git clone, so there's nothing to pull. If you "
            "installed Chronicle with `uv tool install chronicle-memory`, update it with "
            "`uv tool upgrade chronicle-memory`. If you installed it as a Claude Code "
            "plugin, use scripts/update.ps1 (Windows) or scripts/update.sh, or "
            "`/plugin update chronicle` inside Claude Code."
        )
    if shutil.which("git") is None:
        raise UpdateError("git is not installed or not on PATH.")
    if _git(repo, "status", "--porcelain", "--untracked-files=no"):
        raise UpdateError(
            "you have uncommitted changes in the chronicle folder; commit or "
            "stash them first, then run `chronicle update` again."
        )

    old = _git(repo, "rev-parse", "HEAD")
    branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    _say(f"Fetching the latest {BRANCH} from {REMOTE}...")
    _git(repo, "fetch", REMOTE, BRANCH)
    if branch != BRANCH:
        _say(f"Switching from branch '{branch}' to '{BRANCH}'...")
        _git(repo, "switch", BRANCH)
    result = _run(["git", "merge", "--ff-only", f"{REMOTE}/{BRANCH}"], repo, capture_output=True)
    if result.returncode != 0:
        raise UpdateError(
            f"your local '{BRANCH}' has commits that aren't on {REMOTE}/{BRANCH}, "
            "so it can't be fast-forwarded. Push or reset them, then try again."
        )
    return old, _git(repo, "rev-parse", "HEAD")


def _sync_dependencies(repo: Path) -> None:
    prefix = Path(sys.prefix).resolve()
    if prefix == (repo / ".venv").resolve():
        # Running via `uv run`: uv re-syncs this env by itself on next run.
        return
    _say("Checking dependencies...")
    env = dict(os.environ, VIRTUAL_ENV=str(prefix))
    # --no-install-project: chronicle itself is an editable install, so it
    # needs no reinstall; reinstalling would replace the chronicle.exe that is
    # running this very command, which Windows refuses ("Access is denied").
    result = _run(
        ["uv", "sync", "--active", "--project", str(repo), "--no-dev", "--inexact", "--no-install-project", "--quiet"],
        repo,
        env=env,
    )
    if result.returncode != 0:
        raise UpdateError(
            "updating dependencies failed. On Windows this usually means "
            "another Chronicle process is using them: stop the dashboard "
            "(`chronicle stop`), close Claude Code/Cursor sessions, then run "
            "`chronicle update` again."
        )


def _build_dashboard(repo: Path) -> None:
    npm = shutil.which("npm")
    if npm is None:
        _say(
            "Note: Node.js isn't installed, so the dashboard frontend wasn't "
            "rebuilt. Install Node.js and run `npm ci && npm run build` in the "
            "dashboard folder.",
            file=sys.stderr,
        )
        return
    _say("Rebuilding the dashboard...")
    dashboard = repo / "dashboard"
    for step in (["ci"], ["run", "build"]):
        if _run([npm, *step], dashboard).returncode != 0:
            raise UpdateError(f"`npm {' '.join(step)}` failed in {dashboard}.")


def update(repo: Path) -> None:
    old_version = _version(repo)
    old, new = _update_git(repo)

    # Both steps also run when git had nothing new, so a run that pulled but
    # then failed (e.g. a locked file on Windows) is finished by the next one.
    # The dependency sync is a fast no-op when nothing changed.
    _sync_dependencies(repo)
    if (old != new and _changed(repo, old, new, "dashboard")) or not (
        repo / "dashboard" / "dist" / "index.html"
    ).is_file():
        _build_dashboard(repo)

    if old == new:
        _say(f"Chronicle is already up to date (version {old_version}).")
        return
    _say(f"Updated Chronicle {old_version} -> {_version(repo)}.")
    _say(
        "Restart open Claude Code/Cursor/Codex sessions and any running "
        "dashboard (`chronicle stop`, then `chronicle start`) to use it."
    )


def main(argv: list[str]) -> None:
    argparse.ArgumentParser(
        prog="chronicle update",
        description=f"Update this chronicle clone to the latest {REMOTE}/{BRANCH}.",
    ).parse_args(argv)
    try:
        update(repo_root())
    except UpdateError as error:
        raise SystemExit(f"chronicle update: {error}") from None
