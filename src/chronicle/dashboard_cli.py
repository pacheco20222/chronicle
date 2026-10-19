import argparse
import html
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import uvicorn
from starlette.responses import HTMLResponse
from starlette.staticfiles import StaticFiles

from chronicle import server

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MCP_PATH = "/mcp"


def _port_default() -> int:
    return int(os.environ.get("CHRONICLE_DASHBOARD_PORT", DEFAULT_PORT))


def pid_path() -> Path:
    state_dir = Path(os.environ.get("CHRONICLE_STATE_DIR", Path.home() / ".chronicle"))
    return state_dir / "dashboard.pid"


def _dashboard_dist() -> Path:
    return Path(__file__).resolve().parents[2] / "dashboard" / "dist"


def _build_hint() -> str:
    return f'cd "{_dashboard_dist().parent}"\nnpm ci\nnpm run build'


def _missing_build_page(request) -> HTMLResponse:
    return HTMLResponse(
        "<!doctype html><title>Chronicle dashboard not built</title>"
        "<h1>Chronicle dashboard not built</h1>"
        "<p>The dashboard frontend has not been built yet, so there is nothing "
        "to serve here. Build it once (requires Node.js), then restart "
        "<code>chronicle dashboard start</code>:</p>"
        f"<pre>{html.escape(_build_hint())}</pre>"
        f"<p>The MCP endpoint at <code>{MCP_PATH}</code> works either way.</p>",
        status_code=503,
    )


def build_app():
    app = server.mcp.http_app(
        path=MCP_PATH,
        transport="streamable-http",
        json_response=True,
        stateless_http=True,
        host_origin_protection=True,
    )
    dist = _dashboard_dist()
    if (dist / "index.html").is_file():
        app.mount("/", StaticFiles(directory=dist, html=True), name="dashboard")
    else:
        app.add_route("/", _missing_build_page, methods=["GET"])
    return app


def run_foreground(port: int) -> None:
    print(f"Chronicle dashboard: http://{HOST}:{port}")
    print(f"MCP endpoint: http://{HOST}:{port}{MCP_PATH}")
    if not (_dashboard_dist() / "index.html").is_file():
        print(
            "Warning: dashboard frontend is not built, so the page above will "
            f"only show build instructions. Build it with:\n{_build_hint()}",
            file=sys.stderr,
        )
    uvicorn.run(build_app(), host=HOST, port=port, lifespan="on")


def _pid_is_running(pid: int) -> bool:
    # On Windows, signal 0 is CTRL_C_EVENT, so os.kill(pid, 0) is not a
    # liveness probe there; ask the process handle for its exit code instead.
    if sys.platform == "win32":
        return _windows_pid_is_running(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _windows_pid_is_running(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    ERROR_ACCESS_DENIED = 5

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ctypes.get_last_error() == ERROR_ACCESS_DENIED
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _terminate(pid: int) -> None:
    # On Windows the venv's python.exe is a launcher that spawns the real
    # interpreter as a child, so the recorded PID is not the server itself:
    # kill the whole tree.
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    os.kill(pid, signal.SIGTERM)


def _background_popen_kwargs() -> dict:
    if sys.platform == "win32":
        # A hidden console of its own, so closing the terminal that started
        # it does not take the dashboard down with it.
        return {
            "creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
        }
    return {"start_new_session": True}


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
        [sys.executable, "-m", "chronicle.dashboard_cli", "start", "--port", str(port)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **_background_popen_kwargs(),
    )
    path.write_text(str(child.pid))
    print(f"Chronicle dashboard started in background (PID {child.pid})")


def stop() -> None:
    path = pid_path()
    if not path.exists():
        print("Chronicle dashboard is not running")
        return
    try:
        pid = int(path.read_text().strip())
    except ValueError as exc:
        raise SystemExit(f"invalid dashboard PID file: {path}") from exc

    if not _pid_is_running(pid):
        path.unlink(missing_ok=True)
        print("Removed stale Chronicle dashboard PID file")
        return

    _terminate(pid)
    deadline = time.monotonic() + 3
    while _pid_is_running(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    path.unlink(missing_ok=True)
    print(f"Chronicle dashboard stopped (PID {pid})")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="chronicle dashboard")
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
