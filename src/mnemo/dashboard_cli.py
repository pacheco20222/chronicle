import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import uvicorn
from starlette.staticfiles import StaticFiles

from mnemo import server

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MCP_PATH = "/mcp"


def _port_default() -> int:
    return int(os.environ.get("MNEMO_DASHBOARD_PORT", DEFAULT_PORT))


def pid_path() -> Path:
    state_dir = Path(os.environ.get("MNEMO_STATE_DIR", Path.home() / ".mnemo"))
    return state_dir / "dashboard.pid"


def _dashboard_dist() -> Path:
    return Path(__file__).resolve().parents[2] / "dashboard" / "dist"


def build_app():
    app = server.mcp.http_app(
        path=MCP_PATH,
        transport="streamable-http",
        json_response=True,
        stateless_http=True,
        host_origin_protection=True,
    )
    dist = _dashboard_dist()
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="dashboard")
    return app


def run_foreground(port: int) -> None:
    print(f"Mnemo dashboard: http://{HOST}:{port}")
    print(f"MCP endpoint: http://{HOST}:{port}{MCP_PATH}")
    uvicorn.run(build_app(), host=HOST, port=port, lifespan="on")


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def start_background(port: int) -> None:
    path = pid_path()
    if path.exists():
        try:
            existing_pid = int(path.read_text().strip())
        except ValueError:
            existing_pid = 0
        if existing_pid and _pid_is_running(existing_pid):
            raise SystemExit(f"dashboard already running with PID {existing_pid}")
        path.unlink(missing_ok=True)

    path.parent.mkdir(parents=True, exist_ok=True)
    child = subprocess.Popen(
        [sys.executable, "-m", "mnemo.dashboard_cli", "start", "--port", str(port)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    path.write_text(str(child.pid))
    print(f"Mnemo dashboard started in background (PID {child.pid})")


def stop() -> None:
    path = pid_path()
    if not path.exists():
        print("Mnemo dashboard is not running")
        return
    try:
        pid = int(path.read_text().strip())
    except ValueError as exc:
        raise SystemExit(f"invalid dashboard PID file: {path}") from exc

    if not _pid_is_running(pid):
        path.unlink(missing_ok=True)
        print("Removed stale Mnemo dashboard PID file")
        return

    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 3
    while _pid_is_running(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    path.unlink(missing_ok=True)
    print(f"Mnemo dashboard stopped (PID {pid})")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="mnemo dashboard")
    subparsers = parser.add_subparsers(dest="command")
    start = subparsers.add_parser("start")
    start.add_argument("--background", action="store_true")
    start.add_argument("--port", type=int, default=_port_default())
    subparsers.add_parser("stop")
    if argv is None:
        argv = sys.argv[1:]
    args = parser.parse_args(argv or ["start"])

    if args.command == "stop":
        stop()
        return
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if args.background:
        start_background(args.port)
    else:
        run_foreground(args.port)


if __name__ == "__main__":
    main()
