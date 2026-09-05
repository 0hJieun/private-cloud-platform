"""add instance automation enrollment

Revision ID: 0003_instance_enrollment
Revises: 0002_add_instance_monitoring
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa


# Alembic 기본 version_num은 VARCHAR(32)다. revision ID도 이 한도를 넘기면
# migration DDL 뒤 version table 갱신에서 실패하므로 짧고 안정적인 ID를 사용한다.
revision = "0003_instance_enrollment"
down_revision = "0002_add_instance_monitoring"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 기존 VM에는 control 전용 automation key가 주입된 적이 없다. false로 시작해
    # 다음 생성부터만 runtime inventory에 넣어야 기존 tenant 접근 범위가 바뀌지 않는다.
    # MariaDB는 DDL을 implicit commit한다. 직전처럼 revision version write만 실패한
    # 부분 적용 상태에서도 rerun이 가능하도록 column 존재 여부를 먼저 확인한다.
    existing_columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("instances")}
    if "automation_enrolled" not in existing_columns:
        op.add_column(
            "instances",
            sa.Column("automation_enrolled", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    op.alter_column(
        "instances",
        "automation_enrolled",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("instances", "automation_enrolled")
