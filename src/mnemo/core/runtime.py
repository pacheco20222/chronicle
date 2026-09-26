from mnemo import config
from mnemo.core.qdrant_index import QdrantVectorIndex
from mnemo.core.repository import MemoryRepository
from mnemo.core.service import MemoryService
from mnemo.core.vector_index import VectorIndex
from mnemo.storage.database import Database


_runtime: MemoryService | None = None


def create_runtime(vector_index: VectorIndex | None = None, database: Database | None = None) -> MemoryService:
    database = database or Database(config.sqlite_url())
    return MemoryService(MemoryRepository(database), vector_index or QdrantVectorIndex())


def get_runtime() -> MemoryService:
    global _runtime
    if _runtime is None:
        _runtime = create_runtime()
    return _runtime


def reset_runtime() -> None:
    global _runtime
    _runtime = None
