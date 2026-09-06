"""사용자 VM의 모니터링 여부 열 추가

Revision ID: 0002_add_instance_monitoring
Revises: 0001_initial_control_plane
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_add_instance_monitoring"
down_revision = "0001_initial_control_plane"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 이 버전은 기존 VM을 수집 대상으로 소급 등록하지 않는다.
    # 신규 VM의 기본 활성화 정책은 후속 0004 마이그레이션에서 적용한다.
    op.add_column(
        "instances",
        sa.Column("monitoring_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("instances", "monitoring_enabled", server_default=None)


def downgrade() -> None:
    op.drop_column("instances", "monitoring_enabled")
