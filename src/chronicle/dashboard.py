import json
import subprocess
import sys
from collections import Counter

from chronicle import config, graph_cli, registry


def _docker_status() -> dict:
    try:
        listed = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                "label=com.docker.compose.service=qdrant",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        name = listed.stdout.strip().splitlines()[0] if listed.stdout.strip() else None
        if not name:
            return {"available": False, "health": "not_running"}
        stats = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{.CPUPerc}}\t{{.MemUsage}}", name],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        health = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Health.Status}}", name],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        stats_fields = stats.stdout.strip().split("\t", 1)
        return {
            "available": listed.returncode == 0,
            "name": name,
            "health": health.stdout.strip() or "running",
            "cpu": stats_fields[0] if stats_fields else None,
            "memory": stats_fields[1] if len(stats_fields) == 2 else None,
        }
    except (OSError, subprocess.SubprocessError):
        return {"available": False, "health": "unavailable"}


def _is_uv_run_chronicle(command: str) -> bool:
    # Matches `uv run chronicle` with any uv options in between
    # (`uv --project X run chronicle`) and a full or quoted path to uv/uv.exe.
    tokens = [token.strip("\"'") for token in command.split()]
    for i, token in enumerate(tokens):
        name = token.replace("\\", "/").rsplit("/", 1)[-1].lower()
        if name not in ("uv", "uv.exe"):
            continue
        rest = tokens[i + 1 :]
        if "run" not in rest:
            continue
        # The first positional after `run` is the program uv launches; skip
        # options and their values (`run --project X chronicle`).
        after_option = False
        for arg in rest[rest.index("run") + 1 :]:
            if arg.startswith("-"):
                after_option = "=" not in arg
            elif after_option:
                after_option = False
            else:
                return arg == "chronicle" or arg.startswith("chronicle-")
    return False


_WINDOWS_PROCESS_QUERY = (
    "$procs = @(Get-CimInstance Win32_Process -Filter \"Name='uv.exe'\");"
    "$cpu = @{};"
    "foreach ($p in Get-CimInstance Win32_PerfFormattedData_PerfProc_Process) "
    "{ $cpu[[int]$p.IDProcess] = $p.PercentProcessorTime };"
    "@($procs | ForEach-Object { [pscustomobject]@{ "
    "pid = [int]$_.ProcessId; cpu = $cpu[[int]$_.ProcessId]; "
    "rss_kb = [int64]($_.WorkingSetSize / 1KB); command = $_.CommandLine } }) "
    "| ConvertTo-Json -Compress"
)


def _windows_chronicle_processes() -> list[dict]:
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _WINDOWS_PROCESS_QUERY],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    try:
        rows = json.loads(result.stdout or "[]")
    except ValueError:
        return []
    if isinstance(rows, dict):
        rows = [rows]

    processes = []
    for row in rows:
        command = row.get("command") or ""
        if not _is_uv_run_chronicle(command):
            continue
        try:
            processes.append(
                {
                    "pid": int(row["pid"]),
                    "cpu_percent": str(row.get("cpu") or 0),
                    "rss_kb": int(row.get("rss_kb") or 0),
                    "command": command,
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return processes


def _chronicle_processes() -> list[dict]:
    if sys.platform == "win32":
        return _windows_chronicle_processes()
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,pcpu=,rss=,command="],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    processes = []
    for line in result.stdout.splitlines():
        fields = line.strip().split(None, 3)
        if len(fields) != 4 or not _is_uv_run_chronicle(fields[3]):
            continue
        try:
            processes.append(
                {
                    "pid": int(fields[0]),
                    "cpu_percent": fields[1],
                    "rss_kb": int(fields[2]),
                    "command": fields[3],
                }
            )
        except ValueError:
            continue
    return processes


def build_snapshot(service) -> dict:
    records = service.get_all_with_vectors()
    graph = graph_cli._build_graph_data(records, cross_project=False, current_project=None)
    graph["scopes"] = service.scope_graph_nodes()
    paths_by_project = registry.list_projects()
    records_by_project: dict[str, list[dict]] = {}
    for record in records:
        records_by_project.setdefault(record["project"], []).append(record)

    projects = []
    for project in sorted(set(paths_by_project) | set(records_by_project)):
        project_records = records_by_project.get(project, [])
        project_graph = graph_cli._build_graph_data(
            project_records,
            cross_project=False,
            current_project=project,
        )
        projects.append(
            {
                "name": project,
                "paths": paths_by_project.get(project, []),
                "node_count": service.count(project),
                "edge_count": len(project_graph["edges"]),
                "type_counts": dict(sorted(Counter(r["type"] for r in project_records).items())),
            }
        )

    try:
        qdrant = {
            "healthy": True,
            "collection": config.COLLECTION_NAME,
            "point_count": len(records),
        }
    except Exception as exc:
        qdrant = {
            "healthy": False,
            "collection": config.COLLECTION_NAME,
            "point_count": None,
            "error": type(exc).__name__,
        }

    return {
        "graph": graph,
        "projects": projects,
        "control": {
            "qdrant": qdrant,
            "docker": _docker_status(),
            "chronicle_processes": _chronicle_processes(),
            "sampled": True,
        },
    }
