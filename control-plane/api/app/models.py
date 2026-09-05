"""MariaDB에 저장하는 private-cloud control-plane 상태 model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserRole:
    ADMIN = "admin"
    MEMBER = "member"


class InstanceStatus:
    REQUESTED = "REQUESTED"
    SCHEDULING = "SCHEDULING"
    PROVISIONING = "PROVISIONING"
    WAITING_FOR_IP = "WAITING_FOR_IP"
    ACTIVE = "ACTIVE"
    ERROR = "ERROR"
    DELETE_REQUESTED = "DELETE_REQUESTED"
    DELETING = "DELETING"
    DELETED = "DELETED"


class OperationType:
    CREATE = "CREATE"
    DELETE = "DELETE"
    MIGRATE = "MIGRATE"


class OperationStatus:
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(63), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default=UserRole.MEMBER)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SshPublicKey(Base):
    __tablename__ = "ssh_public_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(63), nullable=False)
    public_key: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(96), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Image(Base):
    __tablename__ = "images"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    os_family: Mapped[str] = mapped_column(String(32), nullable=False)
    os_version: Mapped[str] = mapped_column(String(32), nullable=False)
    disk_format: Mapped[str] = mapped_column(String(16), nullable=False)
    source_path: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ComputeNode(Base):
    __tablename__ = "compute_nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)
    management_address: Mapped[str] = mapped_column(String(45), unique=True, nullable=False)
    provider_address: Mapped[str] = mapped_column(String(45), unique=True, nullable=False)
    allocatable_vcpus: Mapped[int] = mapped_column(Integer, nullable=False)
    allocatable_memory_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="READY")
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Instance(Base):
    """한 VM의 desired state와 실제 배치·IP·오류 결과를 보관한다."""

    __tablename__ = "instances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(63), index=True, nullable=False)
    # 삭제 뒤 NULL로 비워 동일한 이름을 다시 쓸 수 있게 하는 unique 값이다.
    active_name: Mapped[Optional[str]] = mapped_column(String(63), unique=True, nullable=True)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    image_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ssh_public_key_id: Mapped[str] = mapped_column(String(36), nullable=False)
    requested_vcpus: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_memory_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_disk_gb: Mapped[int] = mapped_column(Integer, nullable=False)
    # 새 VM은 guest node exporter를 기본 설치해 platform 관측 대상에 자동 편입한다.
    # 이전 정책에서 생성된 VM은 migration으로 값을 바꾸지 않아 실제 설치 여부를 보존한다.
    monitoring_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # 새 VM은 control의 별도 automation public key를 함께 받아 Ansible runtime
    # inventory에 편입된다. 기존 VM은 해당 키가 없으므로 migration 기본값 false로
    # 남겨, 의도하지 않은 control SSH 접근을 만들지 않는다.
    automation_enrolled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=InstanceStatus.REQUESTED)
    assigned_compute_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    provider_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    guest_username: Mapped[str] = mapped_column(String(63), nullable=False, default="clouduser")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Operation(Base):
    __tablename__ = "operations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    instance_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    operation_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=OperationStatus.PENDING)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class InstanceEvent(Base):
    __tablename__ = "instance_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    operation_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    previous_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    next_status: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
