"""HTTP request·response 형식. 웹 UI는 이 계약만 알고 API를 호출한다."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ImageName(str, Enum):
    ROCKY_9_GENERIC_CLOUD = "rocky-9-genericcloud"


class InstanceCreate(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{0,62}$", examples=["app01"])
    image: ImageName = ImageName.ROCKY_9_GENERIC_CLOUD
    vcpus: int = Field(default=1, ge=1, le=2)
    memory_mb: int = Field(default=1024, ge=512, le=2048)
    disk_gb: int = Field(default=10, ge=10, le=100)


class InstanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    image: str
    requested_vcpus: int
    requested_memory_mb: int
    requested_disk_gb: int
    status: str
    assigned_compute: str | None
    provider_ip: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class ImageRead(BaseModel):
    name: ImageName
    display_name: str
    available: bool


class HealthRead(BaseModel):
    status: str
    environment: str
