"""MariaDB에 저장하는 control-plane 상태 model."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InstanceStatus(str, enum.Enum):
    """worker가 앞으로 전이시킬 인스턴스 lifecycle 상태."""

    REQUESTED = "REQUESTED"
    SCHEDULING = "SCHEDULING"
    PROVISIONING = "PROVISIONING"
    WAITING_FOR_IP = "WAITING_FOR_IP"
    ACTIVE = "ACTIVE"
    ERROR = "ERROR"
    DELETING = "DELETING"
    DELETED = "DELETED"


class Instance(Base):
    """한 VM 생성 요청의 desired state와 관측 결과를 보관한다."""

    __tablename__ = "instances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(63), unique=True, index=True, nullable=False)
    image: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_vcpus: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_memory_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_disk_gb: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=InstanceStatus.REQUESTED.value)
    assigned_compute: Mapped[str | None] = mapped_column(String(63), nullable=True)
    provider_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
