"""HTTP request·response 계약.

DB 모델 자체를 외부에 그대로 노출하지 않는다. 이 파일이 API의 안정적인 경계이며,
웹 화면과 이후 별도 프론트엔드는 이 형식만 사용한다.
"""

from __future__ import annotations

from datetime import datetime

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


class InstanceRead(BaseModel):
    id: str
    name: str
    owner_id: str
    image_id: str
    requested_vcpus: int
    requested_memory_mb: int
    requested_disk_gb: int
    status: str
    assigned_compute: str | None
    provider_ip: str | None
    guest_username: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class OperationRead(BaseModel):
    id: str
    operation_type: str
    status: str
    attempts: int
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class HealthRead(BaseModel):
    status: str
    environment: str
