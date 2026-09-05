"""worker가 만드는 Ansible runtime inventory 형식 검증."""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


os.environ["PRIVATE_CLOUD_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["PRIVATE_CLOUD_INSTANCE_AUTOMATION_PRIVATE_KEY"] = "/tmp/private-cloud-instance-automation"
os.environ["PRIVATE_CLOUD_INSTANCE_KNOWN_HOSTS"] = "/tmp/private-cloud-instance-known-hosts"

WORKER_PATH = Path(__file__).resolve().parents[2] / "control-plane" / "worker" / "worker.py"
SPEC = importlib.util.spec_from_file_location("instance_inventory_worker", WORKER_PATH)
worker = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = worker
SPEC.loader.exec_module(worker)


class RuntimeInventoryTests(unittest.TestCase):
    def test_emits_only_addressable_instances_with_dedicated_automation_key(self):
        active = SimpleNamespace(
            id="instance-1",
            name="web01",
            provider_ip="172.16.8.155",
            guest_username="clouduser",
            monitoring_enabled=True,
        )
        no_ip = SimpleNamespace(
            id="instance-2",
            name="waiting-ip",
            provider_ip=None,
            guest_username="clouduser",
            monitoring_enabled=False,
        )

        payload = worker.runtime_inventory_payload([no_ip, active])

        self.assertEqual(["web01"], payload["instances"]["hosts"])
        hostvars = payload["_meta"]["hostvars"]["web01"]
        self.assertEqual("172.16.8.155", hostvars["ansible_host"])
        self.assertEqual("clouduser", hostvars["ansible_user"])
        self.assertEqual("/tmp/private-cloud-instance-automation", hostvars["ansible_ssh_private_key_file"])
        self.assertTrue(hostvars["ansible_become"])
        self.assertIn("StrictHostKeyChecking=accept-new", hostvars["ansible_ssh_common_args"])

    def test_emits_ssh_aliases_from_the_same_runtime_inventory(self):
        active = SimpleNamespace(
            id="instance-1",
            name="web01",
            provider_ip="172.16.8.155",
            guest_username="clouduser",
            monitoring_enabled=True,
        )

        config = worker.runtime_ssh_config_payload(worker.runtime_inventory_payload([active]))

        self.assertIn("Host web01", config)
        self.assertIn("HostName 172.16.8.155", config)
        self.assertIn("User clouduser", config)
        self.assertIn("IdentityFile /tmp/private-cloud-instance-automation", config)
        self.assertIn("StrictHostKeyChecking accept-new", config)


if __name__ == "__main__":
    unittest.main()
