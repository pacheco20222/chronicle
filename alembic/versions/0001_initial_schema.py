"""create canonical memory schema

Revision ID: 0001_initial_schema
Revises:
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "source",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("locator", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_source_project", "source", ["project"], unique=False)

    op.create_table(
        "episode",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project", sa.String(length=255), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["source.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_episode_project", "episode", ["project"], unique=False)

    op.create_table(
        "memory",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=True),
        sa.Column("episode_id", sa.String(length=36), nullable=True),
        sa.Column("supersedes", sa.String(length=36), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("extraction_method", sa.String(length=128), nullable=True),
        sa.Column("slug", sa.String(length=255), nullable=True),
        sa.Column("valid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("relations", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["episode_id"], ["episode.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["source.id"]),
        sa.ForeignKeyConstraint(["supersedes"], ["memory.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project", "slug", name="uq_memory_project_slug"),
    )
    for name, columns in (
        ("ix_memory_project", ["project"]),
        ("ix_memory_type", ["type"]),
        ("ix_memory_status", ["status"]),
        ("ix_memory_source_id", ["source_id"]),
        ("ix_memory_episode_id", ["episode_id"]),
        ("ix_memory_supersedes", ["supersedes"]),
        ("ix_memory_slug", ["slug"]),
        ("ix_memory_project_status_type", ["project", "status", "type"]),
    ):
        op.create_index(name, "memory", columns, unique=False)

    op.create_table(
        "entity",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_entity_project", "entity", ["project"], unique=False)

    op.create_table(
        "fact",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("subject_entity_id", sa.String(length=36), nullable=False),
        sa.Column("predicate", sa.String(length=255), nullable=False),
        sa.Column("object", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["source.id"]),
        sa.ForeignKeyConstraint(["subject_entity_id"], ["entity.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fact_subject_entity_id", "fact", ["subject_entity_id"], unique=False)
    op.create_index("ix_fact_source_id", "fact", ["source_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_fact_source_id", table_name="fact")
    op.drop_index("ix_fact_subject_entity_id", table_name="fact")
    op.drop_table("fact")
    op.drop_index("ix_entity_project", table_name="entity")
    op.drop_table("entity")
    for name in (
        "ix_memory_project_status_type",
        "ix_memory_slug",
        "ix_memory_supersedes",
        "ix_memory_episode_id",
        "ix_memory_source_id",
        "ix_memory_status",
        "ix_memory_type",
        "ix_memory_project",
    ):
        op.drop_index(name, table_name="memory")
    op.drop_table("memory")
    op.drop_index("ix_episode_project", table_name="episode")
    op.drop_table("episode")
    op.drop_index("ix_source_project", table_name="source")
    op.drop_table("source")
