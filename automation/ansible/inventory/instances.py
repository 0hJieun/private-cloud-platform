#!/usr/bin/env python3
"""control worker가 만든 inner VM runtime inventory를 Ansible에 제공한다.

Git의 hosts.yml에는 control/compute/storage처럼 장기적인 인프라만 보관한다. 이 script는
worker가 MariaDB desired state에서 원자적으로 갱신하는 JSON을 읽어 [instances] 그룹만
반환한다. 실행 중인 VM IP와 private key는 Git에 기록되지 않는다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


INVENTORY_PATH = Path(
    os.environ.get("PRIVATE_CLOUD_INSTANCE_INVENTORY", "/home/user1/.local/share/private-cloud/ansible/instances.json")
).expanduser()
EMPTY_INVENTORY = {"instances": {"hosts": []}, "_meta": {"hostvars": {}}}


def main() -> None:
    try:
        payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or "_meta" not in payload:
            raise ValueError("invalid inventory payload")
    except (OSError, ValueError, json.JSONDecodeError):
        payload = EMPTY_INVENTORY
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
