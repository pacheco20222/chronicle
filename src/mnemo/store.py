import uuid
from datetime import datetime, timezone

from qdrant_client import QdrantClient, models

from mnemo import config

DOCUMENT_NAMESPACE = uuid.UUID("332f0123-010a-412a-bca4-41426a0d7997")


def _document_id(project: str, slug: str) -> str:
    return str(uuid.uuid5(DOCUMENT_NAMESPACE, f"{project}:{slug}"))


def get_client() -> QdrantClient:
    return QdrantClient(url=config.QDRANT_URL)


def ensure_collection(client: QdrantClient, collection: str = config.COLLECTION_NAME) -> None:
    if not client.collection_exists(collection):
        client.create_collection(
            collection_name=collection,
            vectors_config=models.VectorParams(
                size=config.VECTOR_SIZE, distance=models.Distance.COSINE
            ),
        )
    client.create_payload_index(
        collection_name=collection,
        field_name="created_at",
        field_schema=models.PayloadSchemaType.DATETIME,
    )


def add_memory(
    client: QdrantClient,
    vector: list[float],
    content: str,
    project: str,
    type_: str,
    source: str | None = None,
    status: str = "active",
    supersedes: str | None = None,
    collection: str = config.COLLECTION_NAME,
) -> str:
    memory_id = str(uuid.uuid4())
    client.upsert(
        collection_name=collection,
        points=[
            models.PointStruct(
                id=memory_id,
                vector=vector,
                payload={
                    "project": project,
                    "type": type_,
                    "content": content,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "source": source,
                    "status": status,
                    "supersedes": supersedes,
                },
            )
        ],
    )
    if supersedes is not None:
        set_status(client, supersedes, "superseded", collection=collection)
    return memory_id


def set_status(
    client: QdrantClient,
    memory_id: str,
    status: str,
    collection: str = config.COLLECTION_NAME,
) -> None:
    client.set_payload(
        collection_name=collection,
        payload={"status": status},
        points=[memory_id],
    )


def _exclude_superseded_filter(must: list) -> models.Filter:
    return models.Filter(
        must=must,
        must_not=[models.FieldCondition(key="status", match=models.MatchValue(value="superseded"))],
    )


def search_memory(
    client: QdrantClient,
    vector: list[float],
    project: str,
    type_: str | None = None,
    k: int = 5,
    include_superseded: bool = False,
    collection: str = config.COLLECTION_NAME,
) -> list[dict]:
    must = [models.FieldCondition(key="project", match=models.MatchValue(value=project))]
    if type_ is not None:
        must.append(models.FieldCondition(key="type", match=models.MatchValue(value=type_)))
    query_filter = models.Filter(must=must) if include_superseded else _exclude_superseded_filter(must)

    response = client.query_points(
        collection_name=collection,
        query=vector,
        limit=k,
        query_filter=query_filter,
    )
    return [{"id": point.id, "score": point.score, **point.payload} for point in response.points]


def get_latest(
    client: QdrantClient,
    project: str,
    type_: str,
    include_superseded: bool = False,
    collection: str = config.COLLECTION_NAME,
) -> dict | None:
    must = [
        models.FieldCondition(key="project", match=models.MatchValue(value=project)),
        models.FieldCondition(key="type", match=models.MatchValue(value=type_)),
    ]
    scroll_filter = models.Filter(must=must) if include_superseded else _exclude_superseded_filter(must)
    records, _ = client.scroll(
        collection_name=collection,
        scroll_filter=scroll_filter,
        order_by=models.OrderBy(key="created_at", direction="desc"),
        limit=1,
        with_payload=True,
    )
    if not records:
        return None
    record = records[0]
    return {"id": record.id, **record.payload}


def get_recent(
    client: QdrantClient,
    project: str,
    type_: str,
    k: int = 5,
    include_superseded: bool = False,
    collection: str = config.COLLECTION_NAME,
) -> list[dict]:
    must = [
        models.FieldCondition(key="project", match=models.MatchValue(value=project)),
        models.FieldCondition(key="type", match=models.MatchValue(value=type_)),
    ]
    scroll_filter = models.Filter(must=must) if include_superseded else _exclude_superseded_filter(must)
    records, _ = client.scroll(
        collection_name=collection,
        scroll_filter=scroll_filter,
        order_by=models.OrderBy(key="created_at", direction="desc"),
        limit=k,
        with_payload=True,
    )
    return [{"id": r.id, **r.payload} for r in records]


def get_document(
    client: QdrantClient,
    project: str,
    slug: str,
    collection: str = config.COLLECTION_NAME,
) -> dict | None:
    points = client.retrieve(
        collection_name=collection,
        ids=[_document_id(project, slug)],
        with_payload=True,
    )
    if not points:
        return None
    point = points[0]
    return {"id": point.id, **point.payload}


def set_document(
    client: QdrantClient,
    vector: list[float],
    content: str,
    project: str,
    slug: str,
    type_: str,
    collection: str = config.COLLECTION_NAME,
) -> str:
    doc_id = _document_id(project, slug)
    existing = get_document(client, project, slug, collection=collection)
    created_at = existing["created_at"] if existing else datetime.now(timezone.utc).isoformat()
    client.upsert(
        collection_name=collection,
        points=[
            models.PointStruct(
                id=doc_id,
                vector=vector,
                payload={
                    "project": project,
                    "type": type_,
                    "slug": slug,
                    "content": content,
                    "created_at": created_at,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "source": None,
                },
            )
        ],
    )
    return doc_id


def search_memory_global(
    client: QdrantClient,
    vector: list[float],
    type_: str | None = None,
    k: int = 5,
    include_superseded: bool = False,
    collection: str = config.COLLECTION_NAME,
) -> list[dict]:
    must = []
    if type_ is not None:
        must.append(models.FieldCondition(key="type", match=models.MatchValue(value=type_)))
    query_filter = (
        (models.Filter(must=must) if must else None)
        if include_superseded
        else _exclude_superseded_filter(must)
    )

    response = client.query_points(
        collection_name=collection,
        query=vector,
        limit=k,
        query_filter=query_filter,
    )
    return [{"id": point.id, "score": point.score, **point.payload} for point in response.points]


def get_all_with_vectors(
    client: QdrantClient,
    project: str | None = None,
    collection: str = config.COLLECTION_NAME,
) -> list[dict]:
    must = []
    if project is not None:
        must.append(models.FieldCondition(key="project", match=models.MatchValue(value=project)))
    records, _ = client.scroll(
        collection_name=collection,
        scroll_filter=models.Filter(must=must) if must else None,
        limit=10000,
        with_payload=True,
        with_vectors=True,
    )
    return [{"id": r.id, "vector": r.vector, **r.payload} for r in records]
