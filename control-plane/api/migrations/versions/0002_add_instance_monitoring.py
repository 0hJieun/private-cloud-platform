"""add managed instance monitoring

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
    # 기존 VM은 owner의 별도 동의 없이 exporter를 설치하거나 Prometheus target으로
    # 등록하지 않는다. 새 요청만 portal의 monitoring_enabled 값을 명시한다.
    op.add_column(
        "instances",
        sa.Column("monitoring_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("instances", "monitoring_enabled", server_default=None)


def downgrade() -> None:
    op.drop_column("instances", "monitoring_enabled")
