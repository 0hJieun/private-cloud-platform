"""initial control plane schema

Revision ID: 0001_initial_control_plane
Revises:
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_control_plane"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("username", sa.String(length=63), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_table(
        "ssh_public_keys",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(length=63), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(length=96), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("fingerprint", name="uq_ssh_public_keys_fingerprint"),
        sa.UniqueConstraint("owner_id", "name", name="uq_ssh_public_keys_owner_name"),
    )
    op.create_table(
        "images",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("os_family", sa.String(length=32), nullable=False),
        sa.Column("os_version", sa.String(length=32), nullable=False),
        sa.Column("disk_format", sa.String(length=16), nullable=False),
        sa.Column("source_path", sa.String(length=512), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "compute_nodes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=63), nullable=False),
        sa.Column("management_address", sa.String(length=45), nullable=False),
        sa.Column("provider_address", sa.String(length=45), nullable=False),
        sa.Column("allocatable_vcpus", sa.Integer(), nullable=False),
        sa.Column("allocatable_memory_mb", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name", name="uq_compute_nodes_name"),
        sa.UniqueConstraint("management_address", name="uq_compute_nodes_management_address"),
        sa.UniqueConstraint("provider_address", name="uq_compute_nodes_provider_address"),
    )
    op.create_table(
        "instances",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=63), nullable=False),
        sa.Column("active_name", sa.String(length=63), nullable=True),
        sa.Column("owner_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("image_id", sa.String(length=64), sa.ForeignKey("images.id"), nullable=False),
        sa.Column("ssh_public_key_id", sa.String(length=36), sa.ForeignKey("ssh_public_keys.id"), nullable=False),
        sa.Column("requested_vcpus", sa.Integer(), nullable=False),
        sa.Column("requested_memory_mb", sa.Integer(), nullable=False),
        sa.Column("requested_disk_gb", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("assigned_compute_id", sa.String(length=36), sa.ForeignKey("compute_nodes.id"), nullable=True),
        sa.Column("provider_ip", sa.String(length=45), nullable=True),
        sa.Column("guest_username", sa.String(length=63), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("active_name", name="uq_instances_active_name"),
    )
    op.create_index("ix_instances_owner_id", "instances", ["owner_id"])
    op.create_index("ix_instances_name", "instances", ["name"])
    op.create_table(
        "operations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("instance_id", sa.String(length=36), sa.ForeignKey("instances.id"), nullable=False),
        sa.Column("operation_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_operations_instance_id", "operations", ["instance_id"])
    op.create_table(
        "instance_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("instance_id", sa.String(length=36), sa.ForeignKey("instances.id"), nullable=False),
        sa.Column("operation_id", sa.String(length=36), sa.ForeignKey("operations.id"), nullable=True),
        sa.Column("previous_status", sa.String(length=32), nullable=True),
        sa.Column("next_status", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_instance_events_instance_id", "instance_events", ["instance_id"])
    op.create_index("ix_instance_events_operation_id", "instance_events", ["operation_id"])


def downgrade() -> None:
    op.drop_table("instance_events")
    op.drop_table("operations")
    op.drop_table("instances")
    op.drop_table("compute_nodes")
    op.drop_table("images")
    op.drop_table("ssh_public_keys")
    op.drop_table("users")
