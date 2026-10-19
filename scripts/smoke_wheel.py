"""Install a built wheel into a clean virtualenv and exercise it.

Usage: python scripts/smoke_wheel.py dist/chronicle_memory-*.whl [--expect-dashboard]

Catches packaging mistakes (missing migrations, compose file, dashboard build)
that a test run from the git checkout can never see.
"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

CHECK = """
import sys
from chronicle import dashboard_cli, server, services

server.memory_add("Deploy runs on every merge to main", "note")
found = [r["content"] for r in server.memory_search("how does deploy work")]
assert found == ["Deploy runs on every merge to main"], found
assert services.compose_file().is_file(), "docker-compose.yml missing from the wheel"
assert not {"fastembed", "qdrant_client"} & set(sys.modules), "base install loaded semantic deps"
print("dashboard_dist:", (dashboard_cli._dashboard_dist() / "index.html").is_file())
"""


def run(cmd, **kwargs):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kwargs).stdout


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel")
    parser.add_argument("--expect-dashboard", action="store_true")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        venv = tmp_path / "venv"
        run(["uv", "venv", "-q", str(venv)])
        bindir = venv / ("Scripts" if os.name == "nt" else "bin")
        python = bindir / ("python.exe" if os.name == "nt" else "python")
        run(["uv", "pip", "install", "-q", "--python", str(python), args.wheel])

        env = dict(
            os.environ,
            CHRONICLE_SQLITE_PATH=str(tmp_path / "c.db"),
            CHRONICLE_CONFIG_PATH=str(tmp_path / "config.json"),
            CHRONICLE_REGISTRY_PATH=str(tmp_path / "projects.json"),
            CHRONICLE_PROJECT="smoke",
        )
        env.pop("CHRONICLE_SEMANTIC", None)
        out = run([str(python), "-c", CHECK], env=env, cwd=tmp)
        print(out, end="")
        if args.expect_dashboard and "dashboard_dist: True" not in out:
            sys.exit("smoke_wheel: the wheel does not contain the built dashboard")
        version = run([str(bindir / ("chronicle.exe" if os.name == "nt" else "chronicle")), "--version"], env=env, cwd=tmp)
        print(version, end="")
    print("wheel smoke test passed")


if __name__ == "__main__":
    main()
