"""Alembic 기본 version column에 들어갈 수 있는 revision ID인지 확인한다."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


MIGRATIONS = Path(__file__).resolve().parents[2] / "control-plane" / "api" / "migrations" / "versions"
REVISION_PATTERN = re.compile(r'^revision\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)


class MigrationRevisionTests(unittest.TestCase):
    def test_revision_ids_fit_alembic_default_version_column(self):
        for migration in MIGRATIONS.glob("*.py"):
            match = REVISION_PATTERN.search(migration.read_text(encoding="utf-8"))
            self.assertIsNotNone(match, f"revision not found: {migration.name}")
            self.assertLessEqual(len(match.group(1)), 32, migration.name)


if __name__ == "__main__":
    unittest.main()
