from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from mnemo.storage.models import Base


class Database:
    def __init__(self, url: str):
        self.url = url
        self.path = self._path_from_url(url)
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            url,
            connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
        )
        if url.startswith("sqlite"):
            event.listen(self.engine, "connect", self._enable_foreign_keys)
        self._run_migrations()
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    def _run_migrations(self) -> None:
        repository_root = Path(__file__).resolve().parents[3]
        alembic_config = Config(str(repository_root / "alembic.ini"))
        alembic_config.set_main_option("script_location", str(repository_root / "alembic"))
        alembic_config.set_main_option("sqlalchemy.url", self.url)
        with self.engine.connect() as connection:
            alembic_config.attributes["connection"] = connection
            command.upgrade(alembic_config, "head")

    @staticmethod
    def _enable_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    @staticmethod
    def _path_from_url(url: str) -> Path | None:
        if url in {"sqlite://", "sqlite:///:memory:"}:
            return None
        if url.startswith("sqlite:///"):
            return Path(url.removeprefix("sqlite:///")).expanduser().resolve()
        return None
