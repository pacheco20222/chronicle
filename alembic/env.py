from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from mnemo import config
from mnemo.storage.models import Base


if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name)

context.config.set_main_option("sqlalchemy.url", os.environ.get("MNEMO_SQLITE_URL", config.sqlite_url()))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=context.config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        context.config.get_section(context.config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
