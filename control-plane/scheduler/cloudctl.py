#!/usr/bin/env python3
"""control 노드 운영자가 사용하는 최소 private-cloud CLI."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import scheduler


def add_resource_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--name", required=True, help="인스턴스 이름")
    parser.add_argument("--vcpus", type=int, default=1, help="vCPU 수 (기본값: 1)")
    parser.add_argument("--memory-mb", type=int, default=1024, help="메모리 MB (기본값: 1024)")
    parser.add_argument("--disk-gb", type=int, default=10, help="디스크 GB (기본값: 10)")


def add_name_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--name", required=True, help="인스턴스 이름")


def validate_name(name: str) -> None:
    if not scheduler.INSTANCE_NAME_PATTERN.fullmatch(name):
        raise ValueError("--name은 소문자·숫자·하이픈으로 시작하는 63자 이하 이름이어야 합니다.")


def validate_private_key(private_key: Path) -> None:
    if not private_key.is_file():
        raise FileNotFoundError(f"개인키를 찾지 못했습니다: {private_key}")


def capacity_snapshot(private_key: Path, remote_user: str) -> list[scheduler.Capacity]:
    return scheduler.query_capacities(scheduler.default_ansible_directory(), private_key, remote_user)


def schedule_request(args: argparse.Namespace, private_key: Path, execute: bool) -> int:
    scheduler.validate_request(args)
    capacities = capacity_snapshot(private_key, args.remote_user)
    existing = scheduler.find_instance(capacities, args.name)
    if existing:
        raise RuntimeError(f"{args.name}은(는) 이미 {existing.name}에 정의되어 있습니다.")

    selected = scheduler.select_node(capacities, args.vcpus, args.memory_mb)
    scheduler.print_capacity(capacities, selected)
    if not execute:
        print("\n계획 모드입니다. 실제 생성은 cloudctl create를 사용하세요.")
        return 0

    print(f"\n{args.name} 생성 요청을 {selected.name}에 전달합니다.")
    scheduler.execute_provisioner(
        scheduler.default_ansible_directory(),
        selected,
        args.name,
        args.vcpus,
        args.memory_mb,
        args.disk_gb,
    )
    return 0


def list_instances(private_key: Path, remote_user: str) -> int:
    capacities = capacity_snapshot(private_key, remote_user)
    print("NAME\tSTATE\tCOMPUTE\tVCPU\tMEMORY_MB")
    for node in capacities:
        for domain in sorted(node.domains, key=lambda item: item["name"]):
            print(
                f"{domain['name']}\t{domain['state']}\t{node.name}\t"
                f"{domain['vcpus']}\t{domain['memory_mb']}"
            )
    return 0


def delete_instance(args: argparse.Namespace, private_key: Path) -> int:
    validate_name(args.name)
    capacities = capacity_snapshot(private_key, args.remote_user)
    target = scheduler.locate_instance(capacities, args.name)
    print(f"{args.name}을(를) {target.name}에서 정상 종료한 뒤 공유 디스크와 함께 삭제합니다.")
    subprocess.run(
        [
            "ansible-playbook",
            "--limit",
            target.name,
            "-e",
            f"instance_name={args.name}",
            str(scheduler.default_ansible_directory() / "playbooks" / "destroy-instance.yml"),
        ],
        cwd=scheduler.default_ansible_directory(),
        check=True,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="cloudctl", description="private-cloud control CLI")
    parser.add_argument(
        "--private-key",
        type=Path,
        default=Path(os.environ.get("PRIVATE_CLOUD_ANSIBLE_KEY", "~/.ssh/private-cloud-ansible")).expanduser(),
        help="compute SSH 확인에 쓸 control 개인키 경로",
    )
    parser.add_argument("--remote-user", default="user1")
    commands = parser.add_subparsers(dest="command", required=True)

    plan_parser = commands.add_parser("plan", help="생성하지 않고 scheduler 선택 결과만 출력")
    add_resource_arguments(plan_parser)

    create_parser = commands.add_parser("create", help="scheduler 선택 후 inner VM 생성")
    add_resource_arguments(create_parser)

    commands.add_parser("list", help="compute에 정의된 inner VM 목록 출력")

    delete_parser = commands.add_parser("delete", help="정상 종료 후 inner VM과 공유 디스크 삭제")
    add_name_argument(delete_parser)

    args = parser.parse_args()
    validate_private_key(args.private_key)

    if args.command == "plan":
        return schedule_request(args, args.private_key, execute=False)
    if args.command == "create":
        return schedule_request(args, args.private_key, execute=True)
    if args.command == "list":
        return list_instances(args.private_key, args.remote_user)
    if args.command == "delete":
        return delete_instance(args, args.private_key)
    raise RuntimeError(f"지원하지 않는 명령입니다: {args.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"cloudctl 오류: {error}", file=sys.stderr)
        raise SystemExit(1)
