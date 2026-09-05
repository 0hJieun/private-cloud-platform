#!/usr/bin/env python3
"""MariaDB operation queue를 실제 scheduler·Ansible 실행으로 연결하는 worker.

API는 빠르게 DB에 PENDING 요청만 저장한다. 이 독립 process가 한 건씩 꺼내
compute를 선택하고 Ansible을 호출한다. HTTP 요청이 끊기거나 웹 서버가 재시작되어도
작업 기록은 MariaDB에 남기 때문에 상태를 추적할 수 있다.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
API_DIRECTORY = REPOSITORY_ROOT / "control-plane" / "api"
SCHEDULER_DIRECTORY = REPOSITORY_ROOT / "control-plane" / "scheduler"
ANSIBLE_DIRECTORY = REPOSITORY_ROOT / "automation" / "ansible"
WORK_DIRECTORY = Path(os.environ.get("PRIVATE_CLOUD_WORK_DIRECTORY", "/home/user1/.local/share/private-cloud/operations"))
LEASE_FILE = Path("/var/lib/dhcpd/dhcpd.leases")

sys.path[:0] = [str(API_DIRECTORY), str(SCHEDULER_DIRECTORY)]

import scheduler  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    ComputeNode,
    Image,
    Instance,
    InstanceEvent,
    InstanceStatus,
    Operation,
    OperationStatus,
    OperationType,
    SshPublicKey,
)


MAC_PATTERN = re.compile(r"\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b", re.IGNORECASE)
LEASE_PATTERN = re.compile(r"lease\s+(?P<ip>\d+(?:\.\d+){3})\s+\{(?P<body>.*?)\n\}", re.DOTALL)


def now() -> datetime:
    return datetime.now(timezone.utc)


def add_event(session, instance: Instance, operation: Optional[Operation], previous: Optional[str], next_status: str, message: str) -> None:
    session.add(
        InstanceEvent(
            instance_id=instance.id,
            operation_id=operation.id if operation else None,
            previous_status=previous,
            next_status=next_status,
            message=message,
        )
    )


def claim_next_operation() -> Optional[str]:
    """단일 worker가 처리할 다음 PENDING 작업을 RUNNING으로 원자적으로 바꾼다."""

    with SessionLocal.begin() as session:
        operation = session.scalar(
            select(Operation)
            .where(Operation.status == OperationStatus.PENDING)
            .order_by(Operation.created_at)
            # 이 랩은 worker service를 한 개만 실행한다. MariaDB 10.5는
            # SKIP LOCKED를 지원하지 않으므로, 이식성 있는 일반 행 잠금만 사용한다.
            # worker를 수평 확장할 때는 DB 버전에 맞는 queue/lock 전략을 별도 설계한다.
            .with_for_update()
        )
        if not operation:
            return None
        operation.status = OperationStatus.RUNNING
        operation.attempts += 1
        operation.started_at = now()
        instance = session.get(Instance, operation.instance_id)
        if not instance:
            operation.status = OperationStatus.FAILED
            operation.error_message = "연결된 인스턴스 레코드를 찾지 못했습니다."
            operation.completed_at = now()
            return None
        previous = instance.status
        target = InstanceStatus.SCHEDULING if operation.operation_type == OperationType.CREATE else InstanceStatus.DELETING
        instance.status = target
        add_event(session, instance, operation, previous, target, "worker가 작업을 가져와 처리하기 시작했습니다.")
        return operation.id


def set_create_placement(operation_id: str, compute_name: str) -> tuple[Instance, Image, SshPublicKey]:
    with SessionLocal.begin() as session:
        operation = session.get(Operation, operation_id)
        instance = session.get(Instance, operation.instance_id) if operation else None
        if not operation or not instance:
            raise RuntimeError("작업 또는 인스턴스 레코드를 찾지 못했습니다.")
        image = session.get(Image, instance.image_id)
        ssh_key = session.get(SshPublicKey, instance.ssh_public_key_id)
        compute = session.scalar(select(ComputeNode).where(ComputeNode.name == compute_name))
        if not image or not image.is_enabled:
            raise RuntimeError("선택한 이미지가 없거나 비활성 상태입니다.")
        if not ssh_key or not ssh_key.is_active:
            raise RuntimeError("선택한 SSH 공개키가 없거나 비활성 상태입니다.")
        if not compute:
            raise RuntimeError(f"DB에서 {compute_name} compute 노드를 찾지 못했습니다.")
        previous = instance.status
        instance.status = InstanceStatus.PROVISIONING
        instance.assigned_compute_id = compute.id
        instance.error_message = None
        compute.state = "READY"
        compute.last_seen_at = now()
        add_event(session, instance, operation, previous, InstanceStatus.PROVISIONING, f"scheduler가 {compute_name}을(를) 선택했습니다.")
        # Session이 닫힌 뒤에도 worker가 필요한 scalar 값만 복사한다.
        session.flush()
        detached_instance = Instance(
            id=instance.id,
            name=instance.name,
            requested_vcpus=instance.requested_vcpus,
            requested_memory_mb=instance.requested_memory_mb,
            requested_disk_gb=instance.requested_disk_gb,
            monitoring_enabled=instance.monitoring_enabled,
        )
        detached_image = Image(id=image.id, source_path=image.source_path, display_name=image.display_name, os_family=image.os_family, os_version=image.os_version, disk_format=image.disk_format, sha256=image.sha256)
        detached_key = SshPublicKey(id=ssh_key.id, public_key=ssh_key.public_key, name=ssh_key.name, owner_id=ssh_key.owner_id, fingerprint=ssh_key.fingerprint)
        return detached_instance, detached_image, detached_key


def write_owner_key(operation_id: str, public_key: str) -> Path:
    work_path = WORK_DIRECTORY / operation_id
    work_path.mkdir(mode=0o700, parents=True, exist_ok=True)
    key_path = work_path / "owner-key.pub"
    key_path.write_text(public_key.strip() + "\n", encoding="utf-8")
    key_path.chmod(0o600)
    return key_path


def execute_provisioner(compute_name: str, instance: Instance, image: Image, owner_key_path: Path) -> None:
    command = [
        "ansible-playbook",
        "--limit",
        compute_name,
        "-e",
        f"instance_name={instance.name}",
        "-e",
        f"instance_vcpus={instance.requested_vcpus}",
        "-e",
        f"instance_memory_mb={instance.requested_memory_mb}",
        "-e",
        f"instance_disk_size_gb={instance.requested_disk_gb}",
        "-e",
        f"instance_cloud_image_path={image.source_path}",
        "-e",
        "instance_ssh_user=clouduser",
        "-e",
        f"instance_monitoring_enabled={'true' if instance.monitoring_enabled else 'false'}",
        "-e",
        f"instance_owner_ssh_public_key_path={owner_key_path}",
        str(ANSIBLE_DIRECTORY / "playbooks" / "provision-instance.yml"),
    ]
    result = subprocess.run(command, cwd=ANSIBLE_DIRECTORY, text=True, capture_output=True, check=False)
    if result.returncode:
        tail = (result.stderr or result.stdout)[-3000:]
        raise RuntimeError(f"Ansible VM 생성 실패:\n{tail}")


def find_guest_mac(compute_name: str, instance_name: str) -> Optional[str]:
    inventory = scheduler.load_compute_hosts(ANSIBLE_DIRECTORY / "inventory" / "hosts.yml", ANSIBLE_DIRECTORY)
    host = next((item for item in inventory if item["name"] == compute_name), None)
    if not host:
        return None
    key_path = Path(os.environ.get("PRIVATE_CLOUD_ANSIBLE_KEY", "~/.ssh/private-cloud-ansible")).expanduser()
    output = scheduler.run(
        [
            "ssh", "-i", str(key_path), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            f"user1@{host['ansible_host']}", "sudo", "-n", "virsh", "-c", "qemu:///system", "domiflist", instance_name,
        ]
    )
    addresses = MAC_PATTERN.findall(output)
    return addresses[-1].lower() if addresses else None


def lease_ip_for_mac(mac: str) -> Optional[str]:
    """ISC dhcpd lease history에서 해당 MAC의 가장 최근 active lease IP를 찾는다."""

    if not LEASE_FILE.is_file():
        return None
    latest_ip: Optional[str] = None
    for match in LEASE_PATTERN.finditer(LEASE_FILE.read_text(encoding="utf-8", errors="replace")):
        body = match.group("body").lower()
        if f"hardware ethernet {mac.lower()};" in body and "binding state active;" in body:
            latest_ip = match.group("ip")
    return latest_ip


def mark_create_finished(operation_id: str, provider_ip: Optional[str]) -> None:
    with SessionLocal.begin() as session:
        operation = session.get(Operation, operation_id)
        instance = session.get(Instance, operation.instance_id) if operation else None
        if not operation or not instance:
            return
        previous = instance.status
        instance.provider_ip = provider_ip
        instance.status = InstanceStatus.ACTIVE if provider_ip else InstanceStatus.WAITING_FOR_IP
        operation.status = OperationStatus.SUCCEEDED
        operation.completed_at = now()
        message = "VM 생성이 완료되고 DHCP 주소를 확인했습니다." if provider_ip else "VM 생성은 완료됐고 DHCP 주소를 기다리고 있습니다."
        add_event(session, instance, operation, previous, instance.status, message)


def execute_destroyer(compute_name: str, instance_name: str) -> None:
    command = [
        "ansible-playbook", "--limit", compute_name, "-e", f"instance_name={instance_name}",
        str(ANSIBLE_DIRECTORY / "playbooks" / "destroy-instance.yml"),
    ]
    result = subprocess.run(command, cwd=ANSIBLE_DIRECTORY, text=True, capture_output=True, check=False)
    if result.returncode:
        tail = (result.stderr or result.stdout)[-3000:]
        raise RuntimeError(f"Ansible VM 삭제 실패:\n{tail}")


def mark_delete_finished(operation_id: str) -> None:
    with SessionLocal.begin() as session:
        operation = session.get(Operation, operation_id)
        instance = session.get(Instance, operation.instance_id) if operation else None
        if not operation or not instance:
            return
        previous = instance.status
        instance.status = InstanceStatus.DELETED
        instance.active_name = None
        instance.provider_ip = None
        instance.deleted_at = now()
        operation.status = OperationStatus.SUCCEEDED
        operation.completed_at = now()
        add_event(session, instance, operation, previous, InstanceStatus.DELETED, "VM domain과 인스턴스 디스크를 정상 삭제했습니다.")


def mark_failed(operation_id: str, error: Exception) -> None:
    with SessionLocal.begin() as session:
        operation = session.get(Operation, operation_id)
        instance = session.get(Instance, operation.instance_id) if operation else None
        if not operation or not instance:
            return
        previous = instance.status
        instance.status = InstanceStatus.ERROR
        instance.error_message = str(error)[-4000:]
        operation.status = OperationStatus.FAILED
        operation.error_message = instance.error_message
        operation.completed_at = now()
        add_event(session, instance, operation, previous, InstanceStatus.ERROR, "worker 처리 중 오류가 발생했습니다.")


def reconcile_waiting_for_ip() -> None:
    """VM은 이미 만들었지만 DHCP가 늦은 경우를 다음 polling에서 ACTIVE로 승격한다."""

    with SessionLocal() as session:
        waiting = list(session.scalars(select(Instance).where(Instance.status == InstanceStatus.WAITING_FOR_IP)))
        work = [(item.id, item.name, item.assigned_compute_id) for item in waiting]
    for instance_id, instance_name, compute_id in work:
        with SessionLocal() as session:
            compute = session.get(ComputeNode, compute_id) if compute_id else None
            compute_name = compute.name if compute else None
        if not compute_name:
            continue
        try:
            mac = find_guest_mac(compute_name, instance_name)
            provider_ip = lease_ip_for_mac(mac) if mac else None
        except RuntimeError:
            continue
        if provider_ip:
            with SessionLocal.begin() as session:
                instance = session.get(Instance, instance_id)
                if instance and instance.status == InstanceStatus.WAITING_FOR_IP:
                    previous = instance.status
                    instance.status = InstanceStatus.ACTIVE
                    instance.provider_ip = provider_ip
                    add_event(session, instance, None, previous, InstanceStatus.ACTIVE, "DHCP 주소 확인이 완료됐습니다.")


def process(operation_id: str) -> None:
    with SessionLocal() as session:
        operation = session.get(Operation, operation_id)
        instance = session.get(Instance, operation.instance_id) if operation else None
        if not operation or not instance:
            return
        operation_type = operation.operation_type
        instance_name = instance.name
        assigned_compute_id = instance.assigned_compute_id
        requested_vcpus = instance.requested_vcpus
        requested_memory_mb = instance.requested_memory_mb

    try:
        if operation_type == OperationType.CREATE:
            key_path = Path(os.environ.get("PRIVATE_CLOUD_ANSIBLE_KEY", "~/.ssh/private-cloud-ansible")).expanduser()
            capacities = scheduler.query_capacities(ANSIBLE_DIRECTORY, key_path, "user1")
            existing = scheduler.find_instance(capacities, instance_name)
            if existing:
                raise RuntimeError(f"{instance_name}은(는) 이미 {existing.name}에 존재합니다.")
            selected = scheduler.select_node(capacities, requested_vcpus, requested_memory_mb)
            detached_instance, image, ssh_key = set_create_placement(operation_id, selected.name)
            owner_key_path = write_owner_key(operation_id, ssh_key.public_key)
            execute_provisioner(selected.name, detached_instance, image, owner_key_path)
            mac = find_guest_mac(selected.name, instance_name)
            provider_ip = None
            for _ in range(12):
                provider_ip = lease_ip_for_mac(mac) if mac else None
                if provider_ip:
                    break
                time.sleep(5)
            mark_create_finished(operation_id, provider_ip)
        elif operation_type == OperationType.DELETE:
            with SessionLocal() as session:
                compute = session.get(ComputeNode, assigned_compute_id) if assigned_compute_id else None
                compute_name = compute.name if compute else None
            if not compute_name:
                raise RuntimeError("삭제할 VM의 배치 compute 정보를 찾지 못했습니다.")
            execute_destroyer(compute_name, instance_name)
            mark_delete_finished(operation_id)
        else:
            raise RuntimeError(f"지원하지 않는 작업 종류입니다: {operation_type}")
    except Exception as error:  # worker는 실패를 DB에 기록하고 다음 요청을 계속 처리한다.
        mark_failed(operation_id, error)


def main() -> int:
    interval = max(int(os.environ.get("PRIVATE_CLOUD_WORKER_INTERVAL_SECONDS", "5")), 1)
    WORK_DIRECTORY.mkdir(mode=0o700, parents=True, exist_ok=True)
    while True:
        reconcile_waiting_for_ip()
        operation_id = claim_next_operation()
        if operation_id:
            process(operation_id)
        else:
            time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
