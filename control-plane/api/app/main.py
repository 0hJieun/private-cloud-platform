"""private-cloud control API의 첫 HTTP 계약.

POST는 MariaDB에 REQUESTED 상태를 남긴다. 실제 scheduler·Ansible 실행은 다음
worker 단계에서 수행한다. 요청 기록과 실행 worker를 분리해야 HTTP 재시도와
실패 상태를 안전하게 처리할 수 있다.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base, engine, get_session
from app.models import Instance, InstanceStatus
from app.schemas import HealthRead, ImageName, ImageRead, InstanceCreate, InstanceRead


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # 첫 배포의 schema bootstrap이다. 구조 변경부터는 Alembic migration으로 전환한다.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Private Cloud Control API",
    version="0.1.0",
    description="인스턴스 요청을 MariaDB에 기록하고 worker에 전달하는 control-plane API",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthRead, tags=["platform"])
def health(session: Session = Depends(get_session)) -> HealthRead:
    session.execute(text("SELECT 1"))
    return HealthRead(status="ok", environment=get_settings().environment)


@app.get("/v1/images", response_model=list[ImageRead], tags=["images"])
def list_images() -> list[ImageRead]:
    # 현재 검증을 마친 이미지는 Rocky 한 종류다. Ubuntu는 이미지 카탈로그 단계에서 추가한다.
    return [
        ImageRead(
            name=ImageName.ROCKY_9_GENERIC_CLOUD,
            display_name="Rocky Linux 9 GenericCloud",
            available=True,
        )
    ]


@app.get("/v1/instances", response_model=list[InstanceRead], tags=["instances"])
def list_instances(session: Session = Depends(get_session)) -> list[Instance]:
    return list(session.scalars(select(Instance).order_by(Instance.created_at.desc())))


@app.get("/v1/instances/{instance_id}", response_model=InstanceRead, tags=["instances"])
def get_instance(instance_id: str, session: Session = Depends(get_session)) -> Instance:
    instance = session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="인스턴스를 찾지 못했습니다.")
    return instance


@app.post(
    "/v1/instances",
    response_model=InstanceRead,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["instances"],
)
def request_instance(payload: InstanceCreate, session: Session = Depends(get_session)) -> Instance:
    instance = Instance(
        name=payload.name,
        image=payload.image.value,
        requested_vcpus=payload.vcpus,
        requested_memory_mb=payload.memory_mb,
        requested_disk_gb=payload.disk_gb,
        status=InstanceStatus.REQUESTED.value,
    )
    session.add(instance)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="같은 이름의 인스턴스 요청이 이미 존재합니다.",
        ) from error
    session.refresh(instance)
    return instance
