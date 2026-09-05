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
    prometheus_url: str
    monitoring_discovery_token: str


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
        # Prometheus는 control의 loopback에만 열어 둔다. 사용자 브라우저가 이 주소를
        # 직접 호출하지 않고, 인증된 API가 필요한 값만 대리 조회한다.
        prometheus_url=os.environ.get("PRIVATE_CLOUD_PROMETHEUS_URL", "http://127.0.0.1:9090"),
        # HTTP service discovery endpoint는 Prometheus process만 호출한다. 빈 기본값은
        # 개발 환경에서 해당 endpoint를 의도적으로 사용할 수 없게 하는 fail-closed 값이다.
        monitoring_discovery_token=os.environ.get("PRIVATE_CLOUD_MONITORING_DISCOVERY_TOKEN", ""),
    )
