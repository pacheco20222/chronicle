from typing import Mapping, Sequence

from chronicle.core.vector_index import VectorHit


class NullVectorIndex:
    """VectorIndex for lexical-only mode: stores nothing, finds nothing.
    Search then relies on SQLite FTS5 alone."""

    stores_vectors = False

    def upsert(self, id: str, vector: Sequence[float], metadata: Mapping[str, str]) -> None:
        return None

    def search(
        self,
        vector: Sequence[float],
        project: str | None,
        k: int,
        filters: Mapping[str, str] | None = None,
    ) -> list[VectorHit]:
        return []

    def delete(self, id: str) -> None:
        return None

    def all(self, project: str | None = None) -> list[dict]:
        return []
