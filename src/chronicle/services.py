import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from chronicle import config

READY_TIMEOUT_SECONDS = 30
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def compose_file() -> Path:
    return Path(__file__).resolve().parents[2] / "docker-compose.yml"


def qdrant_is_reachable(url: str | None = None, timeout: float = 2) -> bool:
    try:
        with urllib.request.urlopen(f"{(url or config.QDRANT_URL).rstrip('/')}/collections", timeout=timeout):
            return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


DOCKER_RUNNING = "running"
DOCKER_NOT_RUNNING = "not_running"
DOCKER_NOT_INSTALLED = "not_installed"

DOCKER_HELP = {
    DOCKER_NOT_INSTALLED: (
        "Docker is not installed. Chronicle runs Qdrant in a Docker container: "
        "install Docker Desktop (https://www.docker.com/products/docker-desktop/), "
        "or OrbStack on macOS, then run `chronicle start` again."
    ),
    DOCKER_NOT_RUNNING: (
        "Docker is installed but not running. Open Docker Desktop (or OrbStack), "
        "wait until it says it's running, then run `chronicle start` again."
    ),
}


def docker_state() -> str:
    if shutil.which("docker") is None:
        return DOCKER_NOT_INSTALLED
    try:
        # `docker info` only succeeds when the daemon answers; the CLI alone
        # being installed isn't enough.
        result = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except OSError:
        return DOCKER_NOT_INSTALLED
    except subprocess.SubprocessError:
        return DOCKER_NOT_RUNNING
    return DOCKER_RUNNING if result.returncode == 0 else DOCKER_NOT_RUNNING


def _is_local_qdrant() -> bool:
    return urlparse(config.QDRANT_URL).hostname in LOCAL_HOSTS


def qdrant_down_message() -> str:
    """What to tell someone whose memory call failed because Qdrant is down."""
    message = f"Chronicle can't reach Qdrant at {config.QDRANT_URL}."
    if not _is_local_qdrant():
        return f"{message} It's a remote URL (CHRONICLE_QDRANT_URL), so check that server."
    state = docker_state()
    if state != DOCKER_RUNNING:
        return f"{message} {DOCKER_HELP[state]}"
    return (
        f"{message} Docker is running but the Qdrant container isn't: run "
        "`chronicle start`, or `docker compose up -d` in the chronicle folder."
    )


def status_lines() -> list[str]:
    """One-glance health for a person who typed plain `chronicle`."""
    if qdrant_is_reachable():
        return [f"Status: ready (Qdrant is running at {config.QDRANT_URL})."]
    return [f"Status: not ready. {qdrant_down_message()}"]


def ensure_qdrant() -> None:
    """Make sure Qdrant answers at CHRONICLE_QDRANT_URL, starting the bundled
    docker compose service when it's a local URL and nothing is listening."""
    if qdrant_is_reachable():
        print(f"Qdrant: running at {config.QDRANT_URL}")
        return

    if not _is_local_qdrant():
        raise SystemExit(
            f"Qdrant is not reachable at {config.QDRANT_URL} (CHRONICLE_QDRANT_URL). "
            "It isn't local, so start it yourself."
        )

    state = docker_state()
    if state != DOCKER_RUNNING:
        raise SystemExit(DOCKER_HELP[state])

    compose = compose_file()
    if not compose.is_file():
        raise SystemExit(f"Qdrant is not running and {compose} was not found to start it.")

    print("Qdrant: not running, starting it with docker compose...")
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", str(compose), "up", "-d"],
            check=False,
        )
    except OSError as error:
        raise SystemExit(DOCKER_HELP[DOCKER_NOT_INSTALLED]) from error
    if result.returncode != 0:
        raise SystemExit("`docker compose up -d` failed; see the Docker output above.")

    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if qdrant_is_reachable():
            print(f"Qdrant: running at {config.QDRANT_URL}")
            return
        time.sleep(0.5)
    print(
        f"Warning: Qdrant was started but isn't answering at {config.QDRANT_URL} yet.",
        file=sys.stderr,
    )
