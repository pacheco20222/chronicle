from collections.abc import Sequence
from datetime import datetime, timezone
import uuid

from mnemo.core.repository import HIDDEN_STATUSES, MemoryRepository, _require_project
from mnemo.core.vector_index import VectorIndex
from mnemo.storage.models import Memory


DOCUMENT_NAMESPACE = uuid.UUID("332f0123-010a-412a-bca4-41426a0d7997")
RRF_K = 60
HYBRID_POOL = 20


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


class MemoryService:
    def __init__(self, repository: MemoryRepository, vector_index: VectorIndex):
        self.repository = repository
        self.vector_index = vector_index

    def _serialize(self, row: Memory, score: float | None = None) -> dict:
        result = {
            "id": row.id,
            "project": row.project,
            "type": row.type,
            "content": row.content,
            "status": row.status,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
            "source_id": row.source_id,
            "source": row.source_record.locator if row.source_record else None,
            "episode_id": row.episode_id,
            "episode_title": row.episode_record.title if row.episode_record else None,
            "supersedes": row.supersedes,
            "confidence": row.confidence,
            "extraction_method": row.extraction_method,
            "slug": row.slug,
            "valid_at": _iso(row.valid_at),
            "invalid_at": _iso(row.invalid_at),
            "relations": list(row.relations or []),
        }
        if score is not None:
            result["score"] = round(score, 6)
        return result

    def add_memory(
        self,
        vector: Sequence[float],
        content: str,
        project: str,
        type_: str,
        source: str | None = None,
        status: str = "active",
        supersedes: str | None = None,
        confidence: float | None = None,
        extraction_method: str | None = None,
    ) -> str:
        project = _require_project(project)
        memory_id = str(uuid.uuid4())
        self.repository.create_memory(
            id=memory_id,
            project=project,
            type_=type_,
            content=content,
            source=source,
            status=status,
            supersedes=supersedes,
            confidence=confidence,
            extraction_method=extraction_method,
        )
        self.vector_index.upsert(memory_id, vector, {"project": project, "type": type_})
        return memory_id

    def set_status(self, memory_id: str, status: str) -> None:
        self.repository.set_status(memory_id, status)

    def link_memories(self, source_id: str, relation_type: str, target_id: str) -> None:
        self.repository.link(source_id, relation_type, target_id)

    def _merge(self, ranked_lists: list[list[str]], rows: dict[str, Memory], k: int) -> list[dict]:
        scores: dict[str, float] = {}
        for ranked in ranked_lists:
            for rank, memory_id in enumerate(ranked, start=1):
                if memory_id in rows:
                    scores[memory_id] = scores.get(memory_id, 0.0) + 1.0 / (RRF_K + rank)
        ordered = sorted(scores, key=lambda memory_id: -scores[memory_id])[:k]
        return [self._serialize(rows[memory_id], scores[memory_id]) for memory_id in ordered]

    def _search(
        self,
        vector: Sequence[float],
        project: str | None,
        query_text: str | None,
        type_: str | None,
        k: int,
        include_superseded: bool,
    ) -> list[dict]:
        pool = max(k * 4, HYBRID_POOL)
        vector_hits = self.vector_index.search(
            vector,
            project,
            pool,
            {"type": type_} if type_ is not None else None,
        )
        ranked_lists = [[hit.id for hit in vector_hits]]
        if query_text and query_text.strip():
            lexical_rows = self.repository.lexical(project, query_text, type_, pool, include_superseded)
            ranked_lists.append([row.id for row in lexical_rows])
        candidate_ids = {memory_id for ranked in ranked_lists for memory_id in ranked}
        rows = self.repository.get_by_ids(candidate_ids)
        rows = {
            memory_id: row
            for memory_id, row in rows.items()
            if row.status != "deleted" and (include_superseded or row.status not in HIDDEN_STATUSES)
        }
        return self._merge(ranked_lists, rows, k)

    def search(
        self,
        vector: Sequence[float],
        project: str,
        query_text: str | None = None,
        type_: str | None = None,
        k: int = 5,
        include_superseded: bool = False,
    ) -> list[dict]:
        project = _require_project(project)
        return self._search(vector, project, query_text, type_, k, include_superseded)

    def search_global(
        self,
        vector: Sequence[float],
        query_text: str | None = None,
        type_: str | None = None,
        k: int = 5,
        include_superseded: bool = False,
    ) -> list[dict]:
        return self._search(vector, None, query_text, type_, k, include_superseded)

    def get_latest(self, project: str, type_: str, include_superseded: bool = False) -> dict | None:
        project = _require_project(project)
        rows = self.repository.recent(project, type_, 1, include_superseded)
        return self._serialize(rows[0]) if rows else None

    def get_recent(self, project: str, type_: str, k: int = 5, include_superseded: bool = False) -> list[dict]:
        project = _require_project(project)
        return [self._serialize(row) for row in self.repository.recent(project, type_, k, include_superseded)]

    def get_document(self, project: str, slug: str) -> dict | None:
        project = _require_project(project)
        row = self.repository.get_document(project, slug)
        return self._serialize(row) if row else None

    def set_document(
        self,
        vector: Sequence[float],
        content: str,
        project: str,
        slug: str,
        type_: str,
        confidence: float | None = None,
        extraction_method: str | None = None,
    ) -> str:
        project = _require_project(project)
        memory_id = str(uuid.uuid5(DOCUMENT_NAMESPACE, f"{project}:{slug}"))
        row = self.repository.upsert_document(
            id=memory_id,
            project=project,
            slug=slug,
            type_=type_,
            content=content,
            confidence=confidence,
            extraction_method=extraction_method,
        )
        self.vector_index.upsert(row.id, vector, {"project": project, "type": type_})
        return row.id

    def get_all_with_vectors(self, project: str | None = None) -> list[dict]:
        indexed = self.vector_index.all(project)
        rows = self.repository.get_by_ids(record["id"] for record in indexed)
        return [
            {**self._serialize(rows[record["id"]]), "vector": record.get("vector")}
            for record in indexed
            if record["id"] in rows
        ]

    def count(self, project: str | None = None) -> int:
        return len(self.repository.all(project))
