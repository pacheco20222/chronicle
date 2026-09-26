from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence


@dataclass(frozen=True)
class VectorHit:
    id: str
    score: float


class VectorIndex(Protocol):
    def upsert(self, id: str, vector: Sequence[float], metadata: Mapping[str, str]) -> None: ...

    def search(
        self,
        vector: Sequence[float],
        project: str | None,
        k: int,
        filters: Mapping[str, str] | None = None,
    ) -> list[VectorHit]: ...

    def delete(self, id: str) -> None: ...

    def all(self, project: str | None = None) -> list[dict]: ...
