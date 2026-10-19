"""add scope hierarchy table, backfilled from existing project values

Revision ID: 0003_scope_hierarchy
Revises: 0002_memory_fts
"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = "0003_scope_hierarchy"
down_revision: Union[str, Sequence[str], None] = "0002_memory_fts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scope",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["scope.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scope_parent_id", "scope", ["parent_id"], unique=False)
    op.create_index("ix_scope_path", "scope", ["path"], unique=True)

    connection = op.get_bind()
    existing = connection.execute(
        text(
            "SELECT DISTINCT project FROM ("
            "SELECT project FROM memory UNION "
            "SELECT project FROM source UNION "
            "SELECT project FROM episode"
            ")"
        )
    ).scalars().all()
    now = connection.execute(text("SELECT CURRENT_TIMESTAMP")).scalar()
    for project in sorted(p for p in existing if p):
        connection.execute(
            text(
                "INSERT INTO scope (id, name, parent_id, path, created_at) "
                "VALUES (:id, :name, NULL, :path, :created_at)"
            ),
            {"id": str(uuid.uuid4()), "name": project, "path": project, "created_at": now},
        )


def downgrade() -> None:
    op.drop_index("ix_scope_path", table_name="scope")
    op.drop_index("ix_scope_parent_id", table_name="scope")
    op.drop_table("scope")
