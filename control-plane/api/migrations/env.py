"""Alembic이 EnvironmentFile의 MariaDB URL을 사용하도록 설정한다."""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.database import Base
import app.models  # noqa: F401 - 모든 model을 Base.metadata에 등록한다.


config = context.config
database_url = os.environ.get("PRIVATE_CLOUD_DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
