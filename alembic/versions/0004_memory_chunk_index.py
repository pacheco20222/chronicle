"""add chunk_index to memory for docs chunking

Revision ID: 0004_memory_chunk_index
Revises: 0003_scope_hierarchy
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_memory_chunk_index"
down_revision: Union[str, Sequence[str], None] = "0003_scope_hierarchy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("memory", sa.Column("chunk_index", sa.Integer(), nullable=True))
    op.create_index("ix_memory_chunk_index", "memory", ["chunk_index"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_memory_chunk_index", table_name="memory")
    op.drop_column("memory", "chunk_index")
