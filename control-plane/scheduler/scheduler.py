#!/usr/bin/env python3
"""작업 처리기와 진단 CLI가 공유하는 compute 자원 조회·배치 로직.

Ansible 인벤토리에서 compute를 찾고 SSH로 실제 libvirt 예약량과 호스트 자원을
확인한다. 웹 요청은 worker가 이 모듈을 호출하고 DB 작업·이력을 관리한다.
직접 실행하는 CLI는 DB를 거치지 않는 진단용 경로이므로, 포털이 관리하는 VM의
생성·삭제에는 포털/API를 사용한다.
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
from typing import Any, Optional


INSTANCE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,62}$")

# 이 코드는 compute 노드에서 stdin으로 실행된다. XML의 memory와 vcpu를 읽어
# domain이 꺼져 있어도 다시 켜질 수 있는 예약 자원으로 계산한다.
REMOTE_CAPACITY_SCRIPT = r'''
import json
import os
import subprocess
import time
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


def cpu_utilization_percent(sample_seconds=0.5):
    """/proc/stat 두 시점의 idle 비율로 host CPU busy 비율을 계산한다.

    load average는 실행 대기 작업 수라 CPU 사용률과 같지 않다. scheduler의 후보
    tie-breaker에는 짧은 구간의 실제 busy 비율이 더 적합하다.
    """

    def read_cpu_times():
        with open("/proc/stat", encoding="utf-8") as stat:
            fields = next(line.split() for line in stat if line.startswith("cpu "))
        values = [int(value) for value in fields[1:]]
        total = sum(values)
        idle = values[3] + (values[4] if len(values) > 4 else 0)  # idle + iowait
        return total, idle

    total_before, idle_before = read_cpu_times()
    time.sleep(sample_seconds)
    total_after, idle_after = read_cpu_times()
    total_delta = total_after - total_before
    idle_delta = idle_after - idle_before
    if total_delta <= 0:
        return 0.0
    return round(100 * (1 - idle_delta / total_delta), 2)


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
            "state": virsh("domstate", name).strip(),
            "memory_mb": memory_kib // 1024,
            "vcpus": vcpus,
        }
    )

print(
    json.dumps(
        {
            "physical_vcpus": os.cpu_count() or 0,
            "cpu_utilization_percent": cpu_utilization_percent(),
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
    cpu_utilization_percent: float
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


def run(command: list[str], *, cwd: Optional[Path] = None, input_text: Optional[str] = None) -> str:
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
    """SSH key로 compute에 접속해 reservation·CPU·메모리 상태를 읽는다."""

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
        cpu_utilization_percent=float(observed["cpu_utilization_percent"]),
        available_memory_mb=int(observed["available_memory_mb"]),
        domains=tuple(observed["domains"]),
    )


def select_node(
    capacities: list[Capacity], request_vcpus: int, request_memory_mb: int
) -> Capacity:
    """수용 가능한 후보 중 VM 수·CPU 사용률·예약 자원이 가장 낮은 노드를 고른다."""

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
            f"CPU {node.cpu_utilization_percent:.1f}%; 실제 가용 {node.available_memory_mb}MB)"
            for node in capacities
        )
        raise RuntimeError(f"요청을 수용할 compute가 없습니다. {details}")

    return min(
        candidates,
        key=lambda node: (
            len(node.domains),
            node.cpu_utilization_percent,
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


def print_capacity(capacities: list[Capacity], selected: Optional[Capacity] = None) -> None:
    print("[compute 자원 상태]")
    for node in capacities:
        marker = " ← 선택" if selected and node.name == selected.name else ""
        print(
            f"- {node.name}: domain {len(node.domains)}개, "
            f"예약 여유 {node.free_vcpus} vCPU / {node.free_memory_mb}MB, "
            f"CPU 사용률 {node.cpu_utilization_percent:.1f}%, "
            f"실제 가용 메모리 {node.available_memory_mb}MB{marker}"
        )


def default_ansible_directory() -> Path:
    """control 저장소 안의 Ansible 실행 경로를 반환한다."""

    return Path(__file__).resolve().parents[2] / "automation" / "ansible"


def query_capacities(
    ansible_directory: Path, private_key: Path, remote_user: str
) -> list[Capacity]:
    """접속 가능한 compute만 scheduler 후보로 반환한다.

    한 노드의 SSH·libvirt 장애가 다른 정상 노드의 신규 VM 요청까지 막지 않게 한다.
    다만 모든 compute가 불가능하면 원인을 포함해 명시적으로 실패한다. 이 함수는
    신규 배치의 후보 수집용이며, down host의 기존 VM 삭제·조작을 성공한 것처럼
    처리하지는 않는다.
    """

    hosts = load_compute_hosts(ansible_directory / "inventory" / "hosts.yml", ansible_directory)
    capacities: list[Capacity] = []
    unavailable: list[str] = []
    for host in hosts:
        try:
            capacities.append(inspect_capacity(host, private_key, remote_user))
        except RuntimeError as error:
            detail = str(error).splitlines()[-1].strip() or "SSH 또는 libvirt 확인 실패"
            unavailable.append(f"{host['name']}: {detail}")
    if not capacities:
        detail = "; ".join(unavailable) or "inventory에 compute 노드가 없습니다."
        raise RuntimeError(f"접속 가능한 compute 노드가 없습니다. {detail}")
    return capacities


def find_instance(capacities: list[Capacity], instance_name: str) -> Optional[Capacity]:
    """정의된 domain 이름으로 유일한 compute를 찾고, 없으면 None을 반환한다."""

    matches = [node for node in capacities if any(domain["name"] == instance_name for domain in node.domains)]
    if len(matches) > 1:
        raise RuntimeError(f"{instance_name}이(가) 여러 compute에 정의되어 있어 안전하게 처리할 수 없습니다.")
    return matches[0] if matches else None


def locate_instance(capacities: list[Capacity], instance_name: str) -> Capacity:
    """삭제처럼 존재가 필수인 작업에 쓸 인스턴스 위치 조회."""

    match = find_instance(capacities, instance_name)
    if not match:
        raise RuntimeError(f"{instance_name} 인스턴스를 찾지 못했습니다.")
    return match


def execute_provisioner(
    ansible_directory: Path,
    selected: Capacity,
    instance_name: str,
    vcpus: int,
    memory_mb: int,
    disk_gb: int,
) -> None:
    """선택된 한 compute만 대상으로 검증된 Ansible 프로비저너를 실행한다."""

    provisioner = ansible_directory / "playbooks" / "provision-instance.yml"
    subprocess.run(
        [
            "ansible-playbook",
            "--limit",
            selected.name,
            "-e",
            f"instance_name={instance_name}",
            "-e",
            f"instance_vcpus={vcpus}",
            "-e",
            f"instance_memory_mb={memory_mb}",
            "-e",
            f"instance_disk_size_gb={disk_gb}",
            str(provisioner),
        ],
        cwd=ansible_directory,
        check=True,
    )


def main() -> int:
    ansible_directory = default_ansible_directory()

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

    capacities = query_capacities(ansible_directory, args.private_key, args.remote_user)

    existing = find_instance(capacities, args.name)
    if existing:
        raise RuntimeError(f"{args.name}은(는) 이미 {existing.name}에 정의되어 있습니다.")

    selected = select_node(capacities, args.vcpus, args.memory_mb)
    print_capacity(capacities, selected)

    if not args.execute:
        print("\n검증 모드입니다. 실제 생성은 --execute를 붙여 다시 실행하세요.")
        return 0

    print(f"\n{args.name} 생성 요청을 {selected.name}에 전달합니다.")
    execute_provisioner(
        ansible_directory,
        selected,
        args.name,
        args.vcpus,
        args.memory_mb,
        args.disk_gb,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"scheduler 오류: {error}", file=sys.stderr)
        raise SystemExit(1)
