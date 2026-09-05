import importlib.util
import sys
import unittest
from pathlib import Path


SCHEDULER_PATH = Path(__file__).resolve().parents[2] / "control-plane" / "scheduler" / "scheduler.py"
SPEC = importlib.util.spec_from_file_location("scheduler", SCHEDULER_PATH)
scheduler = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
# dataclass가 module 이름을 통해 타입 정보를 조회할 수 있도록 등록한다.
sys.modules[SPEC.name] = scheduler
SPEC.loader.exec_module(scheduler)


def capacity(name, domains, available_memory_mb=5000):
    return scheduler.Capacity(
        name=name,
        address="172.16.2.11",
        allocatable_vcpus=2,
        allocatable_memory_mb=4096,
        physical_vcpus=3,
        available_memory_mb=available_memory_mb,
        domains=tuple(domains),
    )


class SelectNodeTests(unittest.TestCase):
    def test_selects_less_allocated_compute(self):
        compute1 = capacity("compute1", [{"name": "demo-web01", "vcpus": 1, "memory_mb": 1024}])
        compute2 = capacity("compute2", [])

        selected = scheduler.select_node([compute1, compute2], 1, 1024)

        self.assertEqual("compute2", selected.name)

    def test_rejects_node_without_reserved_capacity(self):
        full = capacity(
            "compute1",
            [
                {"name": "vm-a", "vcpus": 1, "memory_mb": 2048},
                {"name": "vm-b", "vcpus": 1, "memory_mb": 2048},
            ],
        )

        with self.assertRaises(RuntimeError):
            scheduler.select_node([full], 1, 512)


if __name__ == "__main__":
    unittest.main()
