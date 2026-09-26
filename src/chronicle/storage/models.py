from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import DateTime, Float, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Scope(Base):
    __tablename__ = "scope"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("scope.id"), index=True)
    path: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Source(Base):
    __tablename__ = "source"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False, default="external")
    locator: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Episode(Base):
    __tablename__ = "episode"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source.id"))
    title: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Memory(Base):
    __tablename__ = "memory"
    __table_args__ = (
        UniqueConstraint("project", "slug", name="uq_memory_project_slug"),
        Index("ix_memory_project_status_type", "project", "status", "type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source.id"), index=True)
    episode_id: Mapped[str | None] = mapped_column(ForeignKey("episode.id"), index=True)
    supersedes: Mapped[str | None] = mapped_column(ForeignKey("memory.id"), index=True)
    confidence: Mapped[float | None] = mapped_column(Float)
    extraction_method: Mapped[str | None] = mapped_column(String(128))
    slug: Mapped[str | None] = mapped_column(String(255), index=True)
    valid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    relations: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    chunk_index: Mapped[int | None] = mapped_column(sa.Integer, index=True)

    source_record: Mapped[Source | None] = relationship(lazy="joined")
    episode_record: Mapped[Episode | None] = relationship(lazy="joined")


class Entity(Base):
    __tablename__ = "entity"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)


class Fact(Base):
    __tablename__ = "fact"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject_entity_id: Mapped[str] = mapped_column(ForeignKey("entity.id"), nullable=False, index=True)
    predicate: Mapped[str] = mapped_column(String(255), nullable=False)
    object: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source.id"), index=True)
