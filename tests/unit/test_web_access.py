"""HTTPS 배포 설정과 관리자 Grafana 연결의 회귀 테스트."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "control-plane" / "api"))
os.environ["PRIVATE_CLOUD_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

from fastapi import HTTPException
from app.config import get_settings
from app.main import open_grafana, require_admin
from app.models import UserRole


class WebAccessTests(unittest.TestCase):
    def tearDown(self):
        get_settings.cache_clear()

    def test_https_deployment_enables_secure_session_cookie(self):
        with patch.dict(os.environ, {"PRIVATE_CLOUD_SESSION_HTTPS_ONLY": "true"}):
            get_settings.cache_clear()
            self.assertTrue(get_settings().session_https_only)

    def test_local_development_can_use_http(self):
        with patch.dict(os.environ, {"PRIVATE_CLOUD_SESSION_HTTPS_ONLY": "false"}):
            get_settings.cache_clear()
            self.assertFalse(get_settings().session_https_only)

    def test_grafana_link_uses_configured_public_url(self):
        with patch.dict(os.environ, {"PRIVATE_CLOUD_GRAFANA_URL": "https://grafana.lab.test/"}):
            get_settings.cache_clear()
            response = open_grafana(SimpleNamespace(role=UserRole.ADMIN))
            self.assertEqual(302, response.status_code)
            self.assertEqual("https://grafana.lab.test/d/private-cloud-instances", response.headers["location"])

    def test_member_cannot_pass_grafana_route_admin_dependency(self):
        with self.assertRaises(HTTPException) as error:
            require_admin(SimpleNamespace(role=UserRole.MEMBER))
        self.assertEqual(403, error.exception.status_code)


if __name__ == "__main__":
    unittest.main()
