#!/usr/bin/env python3
"""로컬 VMware 실습용 최소 인스턴스 scheduler.

control에서 실행한다. Ansible inventory로 compute 노드를 찾고 SSH로 libvirt의
정의된 domain 자원량을 읽는다. 가장 덜 할당된 노드를 선택한 뒤, 기존 Ansible
프로비저너를 호출한다. API/DB가 생기기 전의 운영 도구이며, 장기 상태 저장소를
대체하지는 않는다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


INSTANCE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,62}$")

# 이 코드는 compute 노드에서 stdin으로 실행된다. XML의 memory와 vcpu를 읽어
# domain이 꺼져 있어도 다시 켜질 수 있는 예약 자원으로 계산한다.
REMOTE_CAPACITY_SCRIPT = r'''
import json
import os
import subprocess
import xml.etree.ElementTree as ET


def virsh(*arguments):
    return subprocess.check_output(
        ["sudo", "-n", "virsh", "-c", "qemu:///system", *arguments],
        text=True,
    )


def memory_available_mb():
    with open("/proc/meminfo", encoding="utf-8") as meminfo:
        for line in meminfo:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    raise RuntimeError("MemAvailable 값을 찾지 못했습니다.")


domains = []
for name in virsh("list", "--all", "--name").splitlines():
    name = name.strip()
    if not name:
        continue
    root = ET.fromstring(virsh("dumpxml", name))
    memory_kib = int(root.findtext("memory", "0"))
    vcpus = int(root.findtext("vcpu", "0"))
    domains.append(
        {
            "name": name,
            "memory_mb": memory_kib // 1024,
            "vcpus": vcpus,
        }
    )

print(
    json.dumps(
        {
            "physical_vcpus": os.cpu_count() or 0,
            "available_memory_mb": memory_available_mb(),
            "domains": domains,
        }
    )
)
'''


@dataclass(frozen=True)
class Capacity:
    """scheduler가 판단하는 한 compute 노드의 현재 자원 상태."""

    name: str
    address: str
    allocatable_vcpus: int
    allocatable_memory_mb: int
    physical_vcpus: int
    available_memory_mb: int
    domains: tuple[dict[str, Any], ...]

    @property
    def allocated_vcpus(self) -> int:
        return sum(int(domain["vcpus"]) for domain in self.domains)

    @property
    def allocated_memory_mb(self) -> int:
        return sum(int(domain["memory_mb"]) for domain in self.domains)

    @property
    def free_vcpus(self) -> int:
        return self.allocatable_vcpus - self.allocated_vcpus

    @property
    def free_memory_mb(self) -> int:
        return self.allocatable_memory_mb - self.allocated_memory_mb


def run(command: list[str], *, cwd: Path | None = None, input_text: str | None = None) -> str:
    """실패하면 원래 stderr를 보여 주고 즉시 중단하는 subprocess 래퍼."""

    result = subprocess.run(
        command,
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "명령 실행 실패:\n"
            f"  {' '.join(command)}\n"
            f"{result.stderr.strip()}"
        )
    return result.stdout


def load_compute_hosts(inventory_path: Path, ansible_directory: Path) -> list[dict[str, Any]]:
    """Ansible 자체가 해석한 inventory에서 compute host 변수만 가져온다."""

    inventory = json.loads(
        run(
            ["ansible-inventory", "--inventory", str(inventory_path), "--list"],
            cwd=ansible_directory,
        )
    )
    hostvars = inventory["_meta"]["hostvars"]
    compute_names = inventory["compute_nodes"]["hosts"]
    return [{"name": name, **hostvars[name]} for name in compute_names]


def inspect_capacity(host: dict[str, Any], private_key: Path, remote_user: str) -> Capacity:
    """SSH key로 compute에 접속해 libvirt domain 예약량과 host 여유 메모리를 읽는다."""

    output = run(
        [
            "ssh",
            "-i",
            str(private_key),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ConnectTimeout=5",
            f"{remote_user}@{host['ansible_host']}",
            "python3",
            "-",
        ],
        input_text=REMOTE_CAPACITY_SCRIPT,
    )
    observed = json.loads(output)
    return Capacity(
        name=host["name"],
        address=host["ansible_host"],
        allocatable_vcpus=int(host["scheduler_allocatable_vcpus"]),
        allocatable_memory_mb=int(host["scheduler_allocatable_memory_mb"]),
        physical_vcpus=int(observed["physical_vcpus"]),
        available_memory_mb=int(observed["available_memory_mb"]),
        domains=tuple(observed["domains"]),
    )


def select_node(
    capacities: list[Capacity], request_vcpus: int, request_memory_mb: int
) -> Capacity:
    """요청을 수용할 후보 중 예약된 VM 수·메모리·vCPU가 가장 적은 노드를 고른다."""

    candidates = [
        node
        for node in capacities
        if node.free_vcpus >= request_vcpus
        and node.free_memory_mb >= request_memory_mb
        # 실시간 host 메모리가 요청량+512MB보다 작으면 보수적으로 배치하지 않는다.
        and node.available_memory_mb >= request_memory_mb + 512
    ]
    if not candidates:
        details = "; ".join(
            f"{node.name}(여유 정책 {node.free_vcpus} vCPU, {node.free_memory_mb}MB; "
            f"실제 가용 {node.available_memory_mb}MB)"
            for node in capacities
        )
        raise RuntimeError(f"요청을 수용할 compute가 없습니다. {details}")

    return min(
        candidates,
        key=lambda node: (
            len(node.domains),
            node.allocated_memory_mb,
            node.allocated_vcpus,
            node.name,
        ),
    )


def validate_request(args: argparse.Namespace) -> None:
    if not INSTANCE_NAME_PATTERN.fullmatch(args.name):
        raise ValueError("--name은 소문자·숫자·하이픈으로 시작하는 63자 이하 이름이어야 합니다.")
    if not 1 <= args.vcpus <= 2:
        raise ValueError("--vcpus는 이 실습의 VM 크기 정책상 1~2만 허용합니다.")
    if not 512 <= args.memory_mb <= 2048:
        raise ValueError("--memory-mb는 512~2048만 허용합니다.")
    if args.disk_gb < 10:
        raise ValueError("--disk-gb는 10 이상이어야 합니다.")


def print_capacity(capacities: list[Capacity], selected: Capacity) -> None:
    print("[compute 자원 상태]")
    for node in capacities:
        marker = " ← 선택" if node.name == selected.name else ""
        print(
            f"- {node.name}: domain {len(node.domains)}개, "
            f"예약 여유 {node.free_vcpus} vCPU / {node.free_memory_mb}MB, "
            f"실제 가용 메모리 {node.available_memory_mb}MB{marker}"
        )


def main() -> int:
    repository_root = Path(__file__).resolve().parents[2]
    default_ansible_directory = repository_root / "automation" / "ansible"

    parser = argparse.ArgumentParser(description="Ansible 프로비저너를 호출하는 최소 compute scheduler")
    parser.add_argument("--name", required=True, help="생성할 인스턴스 이름")
    parser.add_argument("--vcpus", type=int, default=1, help="요청 vCPU (기본값: 1)")
    parser.add_argument("--memory-mb", type=int, default=1024, help="요청 메모리 MB (기본값: 1024)")
    parser.add_argument("--disk-gb", type=int, default=10, help="요청 디스크 GB (기본값: 10)")
    parser.add_argument(
        "--private-key",
        type=Path,
        default=Path(os.environ.get("PRIVATE_CLOUD_ANSIBLE_KEY", "~/.ssh/private-cloud-ansible")).expanduser(),
        help="compute SSH 확인에 쓸 control의 개인키 경로",
    )
    parser.add_argument("--remote-user", default="user1")
    parser.add_argument("--execute", action="store_true", help="선택 결과로 실제 Ansible 프로비저너를 실행")
    args = parser.parse_args()
    validate_request(args)

    if not args.private_key.is_file():
        raise FileNotFoundError(f"개인키를 찾지 못했습니다: {args.private_key}")

    inventory_path = default_ansible_directory / "inventory" / "hosts.yml"
    hosts = load_compute_hosts(inventory_path, default_ansible_directory)
    capacities = [inspect_capacity(host, args.private_key, args.remote_user) for host in hosts]

    existing = [node.name for node in capacities if any(domain["name"] == args.name for domain in node.domains)]
    if existing:
        raise RuntimeError(f"{args.name}은(는) 이미 {', '.join(existing)}에 정의되어 있습니다.")

    selected = select_node(capacities, args.vcpus, args.memory_mb)
    print_capacity(capacities, selected)

    if not args.execute:
        print("\n검증 모드입니다. 실제 생성은 --execute를 붙여 다시 실행하세요.")
        return 0

    print(f"\n{args.name} 생성 요청을 {selected.name}에 전달합니다.")
    provisioner = default_ansible_directory / "playbooks" / "provision-instance.yml"
    subprocess.run(
        [
            "ansible-playbook",
            "--limit",
            selected.name,
            "-e",
            f"instance_name={args.name}",
            "-e",
            f"instance_vcpus={args.vcpus}",
            "-e",
            f"instance_memory_mb={args.memory_mb}",
            "-e",
            f"instance_disk_size_gb={args.disk_gb}",
            str(provisioner),
        ],
        cwd=default_ansible_directory,
        check=True,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"scheduler 오류: {error}", file=sys.stderr)
        raise SystemExit(1)
