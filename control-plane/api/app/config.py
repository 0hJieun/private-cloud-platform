"""환경 변수 기반 API 설정. 비밀값은 Git이 아니라 control의 EnvironmentFile에 둔다."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    database_url: str
    environment: str
    session_secret: str


@lru_cache
def get_settings() -> Settings:
    # SQLite 기본값은 단위 테스트·로컬 개발에만 쓴다.
    # Ansible 배포는 MariaDB URL을 PRIVATE_CLOUD_DATABASE_URL로 반드시 설정한다.
    return Settings(
        database_url=os.environ.get(
            "PRIVATE_CLOUD_DATABASE_URL", "sqlite+pysqlite:///./private-cloud-development.db"
        ),
        environment=os.environ.get("PRIVATE_CLOUD_ENVIRONMENT", "development"),
        # 배포 playbook은 난수 값을 EnvironmentFile에 저장한다.
        session_secret=os.environ.get("PRIVATE_CLOUD_SESSION_SECRET", "development-only-change-me"),
    )
