from pathlib import Path
import uuid

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


def _alembic_config(url: str) -> Config:
    repo_root = Path(__file__).resolve().parents[1]
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_scope_table_backfills_existing_projects(tmp_path):
    db_path = tmp_path / "pre_scope.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    cfg = _alembic_config(url)

    with engine.connect() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "0002_memory_fts")

    # Simulate pre-existing data from two different projects, written
    # before the scope table existed.
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO source (id, project, kind, locator, created_at) "
                "VALUES (:id, :project, 'external', 'x', '2026-01-01 00:00:00')"
            ),
            {"id": str(uuid.uuid4()), "project": "alpha"},
        )
        connection.execute(
            text(
                "INSERT INTO memory (id, project, type, content, status, "
                "created_at, updated_at, relations) VALUES "
                "(:id, :project, 'note', 'hi', 'active', "
                "'2026-01-01 00:00:00', '2026-01-01 00:00:00', '[]')"
            ),
            {"id": str(uuid.uuid4()), "project": "beta"},
        )

    with engine.connect() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "0003_scope_hierarchy")

    with engine.connect() as connection:
        rows = connection.execute(text("SELECT name, path, parent_id FROM scope ORDER BY name")).all()

    assert [(r.name, r.path, r.parent_id) for r in rows] == [
        ("alpha", "alpha", None),
        ("beta", "beta", None),
    ]

    with engine.connect() as connection:
        cfg.attributes["connection"] = connection
        command.downgrade(cfg, "0002_memory_fts")
    with engine.connect() as connection:
        tables = connection.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='scope'")
        ).all()
    assert tables == []
