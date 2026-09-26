from collections.abc import Mapping, Sequence

from qdrant_client import QdrantClient, models

from mnemo import config
from mnemo.core.vector_index import VectorHit


class QdrantVectorIndex:
    def __init__(
        self,
        client: QdrantClient | None = None,
        collection: str = config.COLLECTION_NAME,
    ):
        self.client = client or QdrantClient(url=config.QDRANT_URL)
        self.collection = collection
        self.ensure_collection()

    def ensure_collection(self) -> None:
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(
                    size=config.VECTOR_SIZE,
                    distance=models.Distance.COSINE,
                ),
            )
        for field in ("project", "type"):
            self.client.create_payload_index(
                collection_name=self.collection,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

    def upsert(self, id: str, vector: Sequence[float], metadata: Mapping[str, str]) -> None:
        self.client.upsert(
            collection_name=self.collection,
            points=[models.PointStruct(id=id, vector=list(vector), payload=dict(metadata))],
        )

    def search(
        self,
        vector: Sequence[float],
        project: str | None,
        k: int,
        filters: Mapping[str, str] | None = None,
    ) -> list[VectorHit]:
        conditions = []
        if project is not None:
            conditions.append(models.FieldCondition(key="project", match=models.MatchValue(value=project)))
        for key, value in (filters or {}).items():
            conditions.append(models.FieldCondition(key=key, match=models.MatchValue(value=value)))
        response = self.client.query_points(
            collection_name=self.collection,
            query=list(vector),
            limit=k,
            query_filter=models.Filter(must=conditions) if conditions else None,
        )
        return [VectorHit(point.id, point.score) for point in response.points]

    def delete(self, id: str) -> None:
        self.client.delete(
            collection_name=self.collection,
            points_selector=models.PointIdsList(points=[id]),
        )

    def all(self, project: str | None = None) -> list[dict]:
        conditions = []
        if project is not None:
            conditions.append(models.FieldCondition(key="project", match=models.MatchValue(value=project)))
        records, _ = self.client.scroll(
            collection_name=self.collection,
            scroll_filter=models.Filter(must=conditions) if conditions else None,
            limit=10000,
            with_payload=True,
            with_vectors=True,
        )
        return [{"id": record.id, "vector": record.vector, **(record.payload or {})} for record in records]
