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


def ensure_qdrant() -> None:
    """Make sure Qdrant answers at CHRONICLE_QDRANT_URL, starting the bundled
    docker compose service when it's a local URL and nothing is listening."""
    if qdrant_is_reachable():
        print(f"Qdrant: running at {config.QDRANT_URL}")
        return

    if urlparse(config.QDRANT_URL).hostname not in LOCAL_HOSTS:
        raise SystemExit(
            f"Qdrant is not reachable at {config.QDRANT_URL} (CHRONICLE_QDRANT_URL). "
            "It isn't local, so start it yourself."
        )

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
        raise SystemExit(
            "Could not run `docker`. Install Docker Desktop (or OrbStack) and make sure it's running."
        ) from error
    if result.returncode != 0:
        raise SystemExit(
            "`docker compose up -d` failed. Is Docker Desktop (or OrbStack) running?"
        )

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
