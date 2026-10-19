from chronicle import config
from chronicle.core.null_index import NullVectorIndex
from chronicle.core.repository import MemoryRepository
from chronicle.core.service import MemoryService
from chronicle.core.vector_index import VectorIndex
from chronicle.storage.database import Database


_runtime: MemoryService | None = None


def create_runtime(vector_index: VectorIndex | None = None, database: Database | None = None) -> MemoryService:
    database = database or Database(config.sqlite_url())
    if vector_index is None:
        if config.semantic_enabled():
            from chronicle.core.qdrant_index import QdrantVectorIndex

            vector_index = QdrantVectorIndex()
        else:
            vector_index = NullVectorIndex()
    return MemoryService(MemoryRepository(database), vector_index)


def get_runtime() -> MemoryService:
    global _runtime
    if _runtime is None:
        _runtime = create_runtime()
    return _runtime


def reset_runtime() -> None:
    global _runtime
    _runtime = None
