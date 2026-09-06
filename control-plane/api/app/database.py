"""SQLAlchemy 연결과 HTTP 요청 단위의 DB 세션 관리."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


settings = get_settings()
engine_options: dict = {"pool_pre_ping": True}
if settings.database_url.startswith("sqlite"):
    # SQLite는 테스트 시 하나의 프로세스 안에서 여러 요청 thread를 허용해야 한다.
    engine_options["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.database_url, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """모든 ORM 모델이 공유하는 테이블 메타데이터의 기준 클래스."""


def get_session() -> Generator[Session, None, None]:
    """요청 한 건에 하나의 session을 만들고 항상 닫는다."""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
