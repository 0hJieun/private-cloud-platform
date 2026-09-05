"""관리자 운영 센터의 예약 자원 집계 회귀 테스트."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


API_ROOT = Path(__file__).resolve().parents[2] / "control-plane" / "api"
sys.path.insert(0, str(API_ROOT))
# import 과정에서 실제 개발 DB 파일을 만들지 않도록 테스트용 메모리 DB를 지정한다.
os.environ["PRIVATE_CLOUD_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

from app.main import admin_overview  # noqa: E402
from app.models import InstanceStatus  # noqa: E402


class FakeSession:
    """admin_overview가 읽는 ORM 결과만 순서대로 제공하는 최소 fake session."""

    def __init__(self, results):
        self.results = list(results)

    def scalars(self, _statement):
        return iter(self.results.pop(0))


class AdminOverviewTests(unittest.TestCase):
    def test_uses_shared_allocation_statuses_for_total_and_node_reservations(self):
        compute1 = SimpleNamespace(
            id="compute-1",
            name="compute1",
            state="READY",
            allocatable_vcpus=2,
            allocatable_memory_mb=4096,
            last_seen_at=None,
        )
        compute2 = SimpleNamespace(
            id="compute-2",
            name="compute2",
            state="READY",
            allocatable_vcpus=2,
            allocatable_memory_mb=4096,
            last_seen_at=None,
        )
        instances = [
            SimpleNamespace(
                assigned_compute_id="compute-1",
                status=InstanceStatus.ACTIVE,
                requested_vcpus=1,
                requested_memory_mb=1024,
            ),
            SimpleNamespace(
                assigned_compute_id="compute-2",
                status=InstanceStatus.DELETING,
                requested_vcpus=1,
                requested_memory_mb=512,
            ),
            SimpleNamespace(
                assigned_compute_id="compute-1",
                status=InstanceStatus.ERROR,
                requested_vcpus=1,
                requested_memory_mb=2048,
            ),
        ]
        session = FakeSession([instances, [compute1, compute2], ["admin"], ["pending-operation"]])

        overview = admin_overview(None, session)

        self.assertEqual(2, overview.active_instances)
        self.assertEqual(1, overview.queued_operations)
        self.assertEqual(1, overview.compute_nodes[0].allocated_vcpus)
        self.assertEqual(1024, overview.compute_nodes[0].allocated_memory_mb)
        self.assertEqual(1, overview.compute_nodes[1].allocated_vcpus)
        self.assertEqual(512, overview.compute_nodes[1].allocated_memory_mb)


if __name__ == "__main__":
    unittest.main()
