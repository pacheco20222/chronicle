import subprocess
from collections import Counter

from mnemo import config, graph_cli, registry, store


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


def _mnemo_processes() -> list[dict]:
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
        if len(fields) != 4 or "uv run mnemo" not in fields[3]:
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


def build_snapshot(client) -> dict:
    records = store.get_all_with_vectors(client)
    graph = graph_cli._build_graph_data(records, cross_project=False, current_project=None)
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
                "node_count": store.count_points(client, project=project),
                "edge_count": len(project_graph["edges"]),
                "type_counts": dict(sorted(Counter(r["type"] for r in project_records).items())),
            }
        )

    try:
        qdrant = {
            "healthy": True,
            "collection": config.COLLECTION_NAME,
            "point_count": store.count_points(client),
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
            "mnemo_processes": _mnemo_processes(),
            "sampled": True,
        },
    }
