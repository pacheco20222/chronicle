from collections.abc import Iterable
from datetime import datetime
import uuid

from sqlalchemy import Select, String, Text, column, select, table, text, update

from chronicle.storage.database import Database
from chronicle.storage.models import Episode, Memory, Scope, Source, utc_now


HIDDEN_STATUSES = {"superseded", "deleted", "wrong"}
memory_fts = table("memory_fts", column("memory_id", String), column("content", Text))


def _fts_phrase(query_text: str) -> str:
    escaped = query_text.replace('"', '""')
    return f'"{escaped}"'


def _require_project(project: str) -> str:
    if not project:
        raise ValueError("project must not be empty")
    return project


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
        confidence: float | None = None,
        extraction_method: str | None = None,
        episode_id: str | None = None,
        chunk_index: int | None = None,
    ) -> Memory:
        project = _require_project(project)
        with self.session_factory() as session:
            source_id = None
            if source is not None:
                source_row = session.scalar(
                    select(Source).where(Source.project == project, Source.locator == source)
                )
                if source_row is None:
                    source_row = Source(id=str(uuid.uuid4()), project=project, locator=source)
                    session.add(source_row)
                source_id = source_row.id
            created_at = utc_now()
            row = Memory(
                id=id,
                project=project,
                type=type_,
                content=content,
                status=status,
                created_at=created_at,
                valid_at=created_at,
                source_id=source_id,
                episode_id=episode_id,
                supersedes=supersedes,
                slug=slug,
                confidence=confidence,
                extraction_method=extraction_method,
                chunk_index=chunk_index,
                relations=[{"type": "supersedes", "target": supersedes}] if supersedes else [],
            )
            session.add(row)
            if supersedes is not None:
                invalid_at = utc_now()
                session.execute(
                    update(Memory)
                    .where(Memory.id == supersedes)
                    .values(status="superseded", invalid_at=invalid_at, updated_at=invalid_at)
                )
            session.commit()
            return row

    def create_episode(self, *, project: str, locator: str, title: str) -> Episode:
        project = _require_project(project)
        with self.session_factory() as session:
            source_row = session.scalar(
                select(Source).where(Source.project == project, Source.locator == locator)
            )
            if source_row is None:
                source_row = Source(id=str(uuid.uuid4()), project=project, locator=locator)
                session.add(source_row)
                session.flush()
            episode = Episode(
                id=str(uuid.uuid4()),
                project=project,
                source_id=source_row.id,
                title=title,
            )
            session.add(episode)
            session.commit()
            return episode

    def upsert_document(
        self,
        *,
        id: str,
        project: str,
        slug: str,
        type_: str,
        content: str,
        confidence: float | None = None,
        extraction_method: str | None = None,
    ) -> Memory:
        project = _require_project(project)
        with self.session_factory() as session:
            row = session.scalar(select(Memory).where(Memory.project == project, Memory.slug == slug))
            if row is None:
                row = Memory(
                    id=id,
                    project=project,
                    slug=slug,
                    type=type_,
                    content=content,
                    confidence=confidence,
                    extraction_method=extraction_method,
                )
                session.add(row)
            else:
                row.type = type_
                row.content = content
                row.confidence = confidence
                row.extraction_method = extraction_method
                row.updated_at = utc_now()
            session.commit()
            return row

    def get(self, memory_id: str) -> Memory | None:
        with self.session_factory() as session:
            return session.scalar(select(Memory).where(Memory.id == memory_id))

    def set_confidence(self, memory_id: str, confidence: float) -> None:
        with self.session_factory() as session:
            session.execute(
                update(Memory)
                .where(Memory.id == memory_id)
                .values(confidence=confidence, updated_at=utc_now())
            )
            session.commit()

    def edit_content(self, memory_id: str, content: str) -> None:
        with self.session_factory() as session:
            session.execute(
                update(Memory)
                .where(Memory.id == memory_id)
                .values(content=content, updated_at=utc_now())
            )
            session.commit()

    def get_by_ids(self, memory_ids: Iterable[str]) -> dict[str, Memory]:
        ids = list(memory_ids)
        if not ids:
            return {}
        with self.session_factory() as session:
            rows = session.scalars(select(Memory).where(Memory.id.in_(ids))).all()
            return {row.id: row for row in rows}

    def get_document(self, project: str, slug: str) -> Memory | None:
        project = _require_project(project)
        with self.session_factory() as session:
            return session.scalar(select(Memory).where(Memory.project == project, Memory.slug == slug))

    def get_active_by_source_locator(self, project: str, locator: str) -> Memory | None:
        project = _require_project(project)
        statement = (
            select(Memory)
            .join(Source, Memory.source_id == Source.id)
            .where(
                Memory.project == project,
                Source.project == project,
                Source.locator == locator,
                Memory.status.not_in(HIDDEN_STATUSES),
            )
            .order_by(Memory.created_at.desc())
            .limit(1)
        )
        with self.session_factory() as session:
            return session.scalar(statement)

    def get_by_source(self, source_id: str) -> list[Memory]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(Memory).where(Memory.source_id == source_id)
            ).all()
            return sorted(rows, key=lambda row: (row.chunk_index is None, row.chunk_index or 0))

    def get_active_by_source_locator_all(self, project: str, locator: str) -> list[Memory]:
        project = _require_project(project)
        statement = (
            select(Memory)
            .join(Source, Memory.source_id == Source.id)
            .where(
                Memory.project == project,
                Source.project == project,
                Source.locator == locator,
                Memory.status.not_in(HIDDEN_STATUSES),
            )
        )
        with self.session_factory() as session:
            rows = session.scalars(statement).all()
            return sorted(rows, key=lambda row: (row.chunk_index is None, row.chunk_index or 0))

    def set_status(self, memory_id: str, status: str) -> None:
        with self.session_factory() as session:
            updated_at = utc_now()
            values = {"status": status, "updated_at": updated_at}
            if status in {"superseded", "expired", "wrong"}:
                values["invalid_at"] = updated_at
            session.execute(
                update(Memory)
                .where(Memory.id == memory_id)
                .values(**values)
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
                    invalid_at = utc_now()
                    target.status = "superseded"
                    target.invalid_at = invalid_at
                    target.updated_at = invalid_at
            session.commit()

    def find_relation_sources(self, relation_type: str, target_id: str) -> list[Memory]:
        with self.session_factory() as session:
            candidates = session.scalars(
                select(Memory).where(Memory.relations.isnot(None))
            ).all()
            return [
                row
                for row in candidates
                if any(
                    relation.get("type") == relation_type and relation.get("target") == target_id
                    for relation in (row.relations or [])
                )
            ]

    def lexical(
        self,
        project: str | None,
        query_text: str,
        type_: str | None,
        limit: int,
        include_superseded: bool,
    ) -> list[Memory]:
        if project is not None:
            project = _require_project(project)
        statement: Select[tuple[Memory]] = (
            select(Memory)
            .join(memory_fts, memory_fts.c.memory_id == Memory.id)
            .where(memory_fts.c.content.match(_fts_phrase(query_text)))
        )
        if project is not None:
            statement = statement.where(Memory.project == project)
        if type_ is not None:
            statement = statement.where(Memory.type == type_)
        if not include_superseded:
            statement = statement.where(Memory.status.not_in(HIDDEN_STATUSES))
        else:
            statement = statement.where(Memory.status != "deleted")
        statement = statement.order_by(text("bm25(memory_fts)"), Memory.created_at.desc()).limit(limit)
        with self.session_factory() as session:
            return list(session.scalars(statement).all())

    def recent(
        self,
        project: str,
        type_: str,
        limit: int,
        include_superseded: bool,
    ) -> list[Memory]:
        project = _require_project(project)
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

    def get_scope_by_path(self, path: str) -> Scope | None:
        with self.session_factory() as session:
            return session.scalar(select(Scope).where(Scope.path == path))

    def get_or_create_scope(self, path: str) -> Scope:
        segments = [segment for segment in path.split("/") if segment]
        if not segments:
            raise ValueError("scope path must not be empty")
        with self.session_factory() as session:
            parent_id = None
            current_path = ""
            scope_row = None
            for segment in segments:
                current_path = f"{current_path}/{segment}" if current_path else segment
                scope_row = session.scalar(select(Scope).where(Scope.path == current_path))
                if scope_row is None:
                    scope_row = Scope(
                        id=str(uuid.uuid4()),
                        name=segment,
                        parent_id=parent_id,
                        path=current_path,
                    )
                    session.add(scope_row)
                    session.flush()
                parent_id = scope_row.id
            session.commit()
            return scope_row

    def list_scopes(self, prefix: str = "") -> list[Scope]:
        with self.session_factory() as session:
            statement = select(Scope)
            if prefix:
                statement = statement.where(
                    (Scope.path == prefix) | (Scope.path.like(f"{prefix}/%"))
                )
            return list(session.scalars(statement.order_by(Scope.path)).all())

    def child_scope_count(self, scope_id: str) -> int:
        with self.session_factory() as session:
            return session.scalar(
                select(text("count(*)")).select_from(Scope).where(Scope.parent_id == scope_id)
            ) or 0

    def reparent_scope(self, path: str, new_parent_path: str | None) -> Scope:
        with self.session_factory() as session:
            scope_row = session.scalar(select(Scope).where(Scope.path == path))
            if scope_row is None:
                raise ValueError(f"no scope found at path {path!r}")

            new_parent_id = None
            new_prefix = ""
            if new_parent_path is not None:
                if new_parent_path == path or new_parent_path.startswith(f"{path}/"):
                    raise ValueError("cannot move a scope under its own descendant")
                parent_row = session.scalar(select(Scope).where(Scope.path == new_parent_path))
                if parent_row is None:
                    raise ValueError(f"no scope found at path {new_parent_path!r}")
                new_parent_id = parent_row.id
                new_prefix = new_parent_path

            old_path = scope_row.path
            new_path = f"{new_prefix}/{scope_row.name}" if new_prefix else scope_row.name
            scope_row.parent_id = new_parent_id
            scope_row.path = new_path
            session.flush()

            descendants = session.scalars(
                select(Scope).where(Scope.path.like(f"{old_path}/%"))
            ).all()
            for descendant in descendants:
                descendant.path = new_path + descendant.path[len(old_path):]

            session.commit()
            return scope_row
