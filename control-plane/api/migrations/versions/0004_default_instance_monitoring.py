"""신규 VM의 모니터링 기본값 활성화

Revision ID: 0004_default_monitoring
Revises: 0003_instance_enrollment
Create Date: 2026-09-06
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_default_monitoring"
down_revision = "0003_instance_enrollment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 기존 VM은 exporter 설치 여부가 다르므로 값을 일괄 변경하지 않는다. 이 DDL 기본값은
    # 이후 생성되는 row에만 적용하며, API도 같은 정책을 명시적으로 강제한다.
    op.alter_column(
        "instances",
        "monitoring_enabled",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=sa.true(),
    )


def downgrade() -> None:
    op.alter_column(
        "instances",
        "monitoring_enabled",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=None,
    )
