"""add FTS5 lexical index for memory content

Revision ID: 0002_memory_fts
Revises: 0001_initial_schema
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0002_memory_fts"
down_revision: Union[str, Sequence[str], None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE VIRTUAL TABLE memory_fts USING fts5(
            memory_id UNINDEXED,
            content
        )
        """
    )
    op.execute(
        """
        CREATE TRIGGER memory_fts_ai AFTER INSERT ON memory
        BEGIN
            INSERT INTO memory_fts(memory_id, content)
            VALUES (new.id, new.content);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER memory_fts_au AFTER UPDATE OF content ON memory
        BEGIN
            DELETE FROM memory_fts WHERE memory_id = old.id;
            INSERT INTO memory_fts(memory_id, content)
            VALUES (new.id, new.content);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER memory_fts_ad AFTER DELETE ON memory
        BEGIN
            DELETE FROM memory_fts WHERE memory_id = old.id;
        END
        """
    )
    op.execute("INSERT INTO memory_fts(memory_id, content) SELECT id, content FROM memory")


def downgrade() -> None:
    op.execute("DROP TRIGGER memory_fts_ad")
    op.execute("DROP TRIGGER memory_fts_au")
    op.execute("DROP TRIGGER memory_fts_ai")
    op.execute("DROP TABLE memory_fts")
