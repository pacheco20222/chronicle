import math


K_NEIGHBORS = 3
MIN_SIMILARITY = 0.3


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def explicit_relations(record: dict) -> list[dict]:
    relations = list(record.get("relations") or [])
    supersedes = record.get("supersedes")
    if supersedes and not any(
        relation.get("type") == "supersedes" and relation.get("target") == supersedes
        for relation in relations
    ):
        relations.append({"type": "supersedes", "target": supersedes})
    return relations


def build_graph_data(
    records: list[dict],
    k: int = K_NEIGHBORS,
    cross_project: bool = False,
    min_similarity: float = MIN_SIMILARITY,
    current_project: str | None = None,
) -> dict:
    n = len(records)
    sim = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                sim[i][j] = cosine(records[i]["vector"], records[j]["vector"])

    edge_set = set()
    for i in range(n):
        candidates = [
            j
            for j in range(n)
            if j != i
            and (cross_project or records[j]["project"] == records[i]["project"])
            and sim[i][j] >= min_similarity
        ]
        neighbors = sorted(candidates, key=lambda j: -sim[i][j])[:k]
        for j in neighbors:
            edge_set.add(tuple(sorted((i, j))))

    latest_checkpoint = {}
    for record in records:
        if record["type"] == "checkpoint" and record.get("created_at", "") > latest_checkpoint.get(record["project"], ("", ""))[0]:
            latest_checkpoint[record["project"]] = (record.get("created_at", ""), record["id"])

    def role(record: dict) -> str:
        if record["type"] == "overview" or (record.get("slug") and record.get("slug") == record["project"]):
            return "core"
        if latest_checkpoint.get(record["project"], ("", None))[1] == record["id"]:
            return "latest"
        return ""

    nodes = [
        {
            "id": record["id"],
            "project": record["project"],
            "type": record["type"],
            "content": record["content"],
            "slug": record.get("slug"),
            "created_at": record.get("created_at"),
            "status": record.get("status") or "active",
            "role": role(record),
        }
        for record in records
    ]
    edges = [
        {
            "source": records[i]["id"],
            "target": records[j]["id"],
            "sim": round(sim[i][j], 3),
            "kind": "semantic",
        }
        for i, j in edge_set
    ]
    id_to_index = {record["id"]: idx for idx, record in enumerate(records)}
    for record in records:
        for relation in explicit_relations(record):
            target = relation.get("target")
            if target not in id_to_index or target == record["id"]:
                continue
            edges.append(
                {
                    "source": record["id"],
                    "target": target,
                    "sim": 0.8,
                    "kind": "explicit",
                    "relation": relation.get("type"),
                }
            )
    return {"nodes": nodes, "edges": edges, "k": k, "current_project": current_project}
