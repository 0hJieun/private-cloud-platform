"""HTTP request·response 계약.

DB 모델 자체를 외부에 그대로 노출하지 않는다. 이 파일이 API의 안정적인 경계이며,
웹 화면과 이후 별도 프론트엔드는 이 형식만 사용한다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=63)
    password: str = Field(min_length=1, max_length=255)


class UserCreate(BaseModel):
    username: str = Field(pattern=r"^[a-z][a-z0-9-]{0,62}$")
    password: str = Field(min_length=12, max_length=255)
    role: str = Field(default="member", pattern=r"^(admin|member)$")


class UserRead(BaseModel):
    id: str
    username: str
    role: str
    is_active: bool
    created_at: datetime


class SshPublicKeyCreate(BaseModel):
    name: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,62}$")
    public_key: str = Field(min_length=32, max_length=16384)


class SshPublicKeyRead(BaseModel):
    id: str
    name: str
    fingerprint: str
    is_active: bool
    created_at: datetime


class ImageRead(BaseModel):
    id: str
    display_name: str
    os_family: str
    os_version: str
    disk_format: str
    sha256: str
    available: bool


class InstanceCreate(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{0,62}$", examples=["app01"])
    image_id: str = Field(min_length=1, max_length=64)
    ssh_public_key_id: str = Field(min_length=36, max_length=36)
    vcpus: int = Field(default=1, ge=1, le=2)
    memory_mb: int = Field(default=1024, ge=512, le=2048)
    disk_gb: int = Field(default=10, ge=10, le=100)
    monitoring_enabled: bool = False


class InstancePreflightRequest(BaseModel):
    """생성 화면의 사전 검사용 입력.

    이 값은 reservation 기반 UX 힌트일 뿐, 실제 생성 시 worker scheduler의
    live capacity 검사를 대체하지 않는다.
    """

    name: str = Field(pattern=r"^[a-z][a-z0-9-]{0,62}$", examples=["app01"])
    vcpus: int = Field(default=1, ge=1, le=2)
    memory_mb: int = Field(default=1024, ge=512, le=2048)
    disk_gb: int = Field(default=10, ge=10, le=100)


class InstancePreflightRead(BaseModel):
    name_available: bool
    capacity_available: bool
    eligible_compute_count: int
    message: str


class InstanceRead(BaseModel):
    id: str
    name: str
    owner_id: str
    # member는 자기 인스턴스만 받으므로 자신의 사용자명만 보며, admin은 전체 VM의
    # 소유자를 사람이 읽을 수 있는 형태로 운영 화면에 표시한다.
    owner_username: str
    image_id: str
    requested_vcpus: int
    requested_memory_mb: int
    requested_disk_gb: int
    monitoring_enabled: bool
    status: str
    assigned_compute: Optional[str]
    provider_ip: Optional[str]
    guest_username: str
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime


class InstanceMonitoringRead(BaseModel):
    """인증된 소유자에게만 노출하는 guest OS 수준의 현재 지표."""

    enabled: bool
    state: str
    provider_ip: Optional[str]
    sampled_at: Optional[datetime]
    cpu_percent: Optional[float]
    memory_percent: Optional[float]
    root_disk_percent: Optional[float]
    network_receive_bytes_per_second: Optional[float]
    network_transmit_bytes_per_second: Optional[float]


class OperationRead(BaseModel):
    id: str
    operation_type: str
    status: str
    attempts: int
    error_message: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class ComputeAllocationRead(BaseModel):
    name: str
    state: str
    allocatable_vcpus: int
    allocatable_memory_mb: int
    allocated_vcpus: int
    allocated_memory_mb: int
    active_instances: int
    last_seen_at: Optional[datetime]


class AdminOverviewRead(BaseModel):
    users: int
    active_instances: int
    queued_operations: int
    compute_nodes: list[ComputeAllocationRead]


class HealthRead(BaseModel):
    status: str
    environment: str
