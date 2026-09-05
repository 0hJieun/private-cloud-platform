"""Alembic이 EnvironmentFile의 MariaDB URL을 사용하도록 설정한다."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Alembic executable은 .venv/bin에서 시작하므로 repository의 app package를 자동으로
# 찾지 못한다. migration 파일 기준 한 단계 위(API project root)를 명시해 개발·Ansible
# 모두 동일하게 `from app...` import를 해석하게 한다.
API_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_PROJECT_ROOT))

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
