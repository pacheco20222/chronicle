from collections.abc import Iterable
from datetime import datetime
import uuid

from sqlalchemy import Select, select, update

from mnemo.storage.database import Database
from mnemo.storage.models import Memory, Source, utc_now


HIDDEN_STATUSES = {"superseded", "deleted"}


class MemoryRepository:
    def __init__(self, database: Database):
        self.database = database
        self.session_factory = database.session_factory

    def create_memory(
        self,
        *,
        id: str,
        project: str,
        type_: str,
        content: str,
        source: str | None = None,
        status: str = "active",
        supersedes: str | None = None,
        slug: str | None = None,
    ) -> Memory:
        with self.session_factory() as session:
            source_id = None
            if source is not None:
                source_row = Source(id=str(uuid.uuid4()), project=project, locator=source)
                session.add(source_row)
                source_id = source_row.id
            row = Memory(
                id=id,
                project=project,
                type=type_,
                content=content,
                status=status,
                source_id=source_id,
                supersedes=supersedes,
                slug=slug,
                relations=[{"type": "supersedes", "target": supersedes}] if supersedes else [],
            )
            session.add(row)
            if supersedes is not None:
                session.execute(
                    update(Memory)
                    .where(Memory.id == supersedes)
                    .values(status="superseded", updated_at=utc_now())
                )
            session.commit()
            return row

    def upsert_document(
        self,
        *,
        id: str,
        project: str,
        slug: str,
        type_: str,
        content: str,
    ) -> Memory:
        with self.session_factory() as session:
            row = session.scalar(select(Memory).where(Memory.project == project, Memory.slug == slug))
            if row is None:
                row = Memory(id=id, project=project, slug=slug, type=type_, content=content)
                session.add(row)
            else:
                row.type = type_
                row.content = content
                row.updated_at = utc_now()
            session.commit()
            return row

    def get(self, memory_id: str) -> Memory | None:
        with self.session_factory() as session:
            return session.scalar(select(Memory).where(Memory.id == memory_id))

    def get_by_ids(self, memory_ids: Iterable[str]) -> dict[str, Memory]:
        ids = list(memory_ids)
        if not ids:
            return {}
        with self.session_factory() as session:
            rows = session.scalars(select(Memory).where(Memory.id.in_(ids))).all()
            return {row.id: row for row in rows}

    def get_document(self, project: str, slug: str) -> Memory | None:
        with self.session_factory() as session:
            return session.scalar(select(Memory).where(Memory.project == project, Memory.slug == slug))

    def set_status(self, memory_id: str, status: str) -> None:
        with self.session_factory() as session:
            session.execute(
                update(Memory)
                .where(Memory.id == memory_id)
                .values(status=status, updated_at=utc_now())
            )
            session.commit()

    def link(self, source_id: str, relation_type: str, target_id: str) -> None:
        with self.session_factory() as session:
            source = session.scalar(select(Memory).where(Memory.id == source_id))
            if source is None:
                raise ValueError(f"no memory found with id {source_id!r}")
            source.relations = [*(source.relations or []), {"type": relation_type, "target": target_id}]
            source.updated_at = utc_now()
            if relation_type == "supersedes":
                target = session.scalar(select(Memory).where(Memory.id == target_id))
                if target is not None:
                    target.status = "superseded"
                    target.updated_at = utc_now()
            session.commit()

    def lexical(
        self,
        project: str | None,
        query_text: str,
        type_: str | None,
        limit: int,
        include_superseded: bool,
    ) -> list[Memory]:
        statement: Select[tuple[Memory]] = select(Memory).where(Memory.content.ilike(f"%{query_text}%"))
        if project is not None:
            statement = statement.where(Memory.project == project)
        if type_ is not None:
            statement = statement.where(Memory.type == type_)
        if not include_superseded:
            statement = statement.where(Memory.status.not_in(HIDDEN_STATUSES))
        else:
            statement = statement.where(Memory.status != "deleted")
        statement = statement.order_by(Memory.created_at.desc()).limit(limit)
        with self.session_factory() as session:
            return list(session.scalars(statement).all())

    def recent(
        self,
        project: str,
        type_: str,
        limit: int,
        include_superseded: bool,
    ) -> list[Memory]:
        statement = select(Memory).where(Memory.project == project, Memory.type == type_)
        if not include_superseded:
            statement = statement.where(Memory.status.not_in(HIDDEN_STATUSES))
        else:
            statement = statement.where(Memory.status != "deleted")
        statement = statement.order_by(Memory.created_at.desc()).limit(limit)
        with self.session_factory() as session:
            return list(session.scalars(statement).all())

    def all(self, project: str | None = None) -> list[Memory]:
        statement = select(Memory)
        if project is not None:
            statement = statement.where(Memory.project == project)
        with self.session_factory() as session:
            return list(session.scalars(statement.order_by(Memory.created_at)).all())
