from dataclasses import dataclass


@dataclass
class Hit:
    id: str
    score: float


class FakeVectorIndex:
    def __init__(self):
        self.points = {}

    def upsert(self, id, vector, metadata):
        self.points[id] = {"vector": list(vector), "metadata": dict(metadata)}

    def search(self, vector, project, k, filters=None):
        hits = []
        for id, point in self.points.items():
            if project is not None and point["metadata"].get("project") != project:
                continue
            if filters and any(point["metadata"].get(key) != value for key, value in filters.items()):
                continue
            score = sum(a * b for a, b in zip(vector, point["vector"]))
            hits.append(Hit(id, score))
        return sorted(hits, key=lambda hit: -hit.score)[:k]

    def delete(self, id):
        self.points.pop(id, None)

    def all(self, project=None):
        return [
            {"id": id, "vector": point["vector"], **point["metadata"]}
            for id, point in self.points.items()
            if project is None or point["metadata"].get("project") == project
        ]
