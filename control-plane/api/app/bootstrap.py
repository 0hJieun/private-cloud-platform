"""첫 배포에서만 기본 사용자·이미지·compute 카탈로그를 채운다.

비밀번호는 코드나 Git에 두지 않는다. deploy playbook이 root 전용 환경 파일에
난수로 만든 뒤 이 모듈을 한 번 실행한다.
"""

from __future__ import annotations

import os

from sqlalchemy import select

from app.database import SessionLocal
from app.models import ComputeNode, Image, User, UserRole
from app.security import hash_password


ROCKY_IMAGE = {
    "id": "rocky-9-genericcloud",
    "display_name": "Rocky Linux 9 GenericCloud",
    "os_family": "rocky",
    "os_version": "9.8",
    "disk_format": "qcow2",
    "source_path": "/var/lib/private-cloud/volumes/images/Rocky-9-GenericCloud-Base-9.8-20260525.0.x86_64.qcow2",
    "sha256": "92c206cc6f790c61583247eefe87890f8828420662c17cacf247cec78ab4eec8",
}

COMPUTE_NODES = (
    {
        "name": "compute1",
        "management_address": "172.16.2.11",
        "provider_address": "172.16.8.11",
        "allocatable_vcpus": 2,
        "allocatable_memory_mb": 4096,
    },
    {
        "name": "compute2",
        "management_address": "172.16.2.12",
        "provider_address": "172.16.8.12",
        "allocatable_vcpus": 2,
        "allocatable_memory_mb": 4096,
    },
)


def required_secret(variable: str) -> str:
    value = os.environ.get(variable, "")
    if len(value) < 12:
        raise RuntimeError(f"{variable} 환경 변수에 12자 이상의 초기 비밀번호가 필요합니다.")
    return value


def ensure_user(session, username: str, password: str, role: str) -> None:
    if session.scalar(select(User).where(User.username == username)) is None:
        session.add(User(username=username, password_hash=hash_password(password), role=role))


def main() -> None:
    admin_password = required_secret("PRIVATE_CLOUD_BOOTSTRAP_ADMIN_PASSWORD")
    member_password = required_secret("PRIVATE_CLOUD_BOOTSTRAP_MEMBER_PASSWORD")
    with SessionLocal() as session:
        ensure_user(session, "admin", admin_password, UserRole.ADMIN)
        ensure_user(session, "member1", member_password, UserRole.MEMBER)
        if session.get(Image, ROCKY_IMAGE["id"]) is None:
            session.add(Image(**ROCKY_IMAGE))
        for node in COMPUTE_NODES:
            if session.scalar(select(ComputeNode).where(ComputeNode.name == node["name"])) is None:
                session.add(ComputeNode(**node))
        session.commit()


if __name__ == "__main__":
    main()
