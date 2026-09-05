"""add instance automation enrollment

Revision ID: 0003_add_instance_automation_enrollment
Revises: 0002_add_instance_monitoring
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_add_instance_automation_enrollment"
down_revision = "0002_add_instance_monitoring"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 기존 VM에는 control 전용 automation key가 주입된 적이 없다. false로 시작해
    # 다음 생성부터만 runtime inventory에 넣어야 기존 tenant 접근 범위가 바뀌지 않는다.
    op.add_column(
        "instances",
        sa.Column("automation_enrolled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("instances", "automation_enrolled", server_default=None)


def downgrade() -> None:
    op.drop_column("instances", "automation_enrolled")
