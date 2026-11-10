"""accounts and shipments

Revision ID: 11e1dcc33061
Revises: aaf5e0667f9e
Create Date: 2026-11-10 20:50:43.466986

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "11e1dcc33061"
down_revision: str | Sequence[str] | None = "aaf5e0667f9e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    json_type = sa.JSON().with_variant(JSONB(), "postgresql")
    op.create_table(
        "login_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_login_codes_email_created", "login_codes", ["email", "created_at"], unique=False
    )
    op.create_index("ix_login_codes_ip_created", "login_codes", ["ip", "created_at"], unique=False)
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "forwarder", "client", "platform", name="orgkind", native_enum=False, length=32
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=True),
        sa.Column("locale", sa.String(length=8), nullable=False),
        sa.Column("is_platform_admin", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("details", json_type, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("apns_token", sa.String(length=256), nullable=False),
        sa.Column("environment", sa.String(length=16), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("apns_token"),
    )
    op.create_index(op.f("ix_devices_user_id"), "devices", ["user_id"], unique=False)
    op.create_table(
        "invitations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column(
            "role",
            sa.Enum("owner", "admin", "agent", "viewer", name="role", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("node_codes", json_type, nullable=False),
        sa.Column("invited_by", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_invitations_org_id"), "invitations", ["org_id"], unique=False)
    op.create_index(op.f("ix_invitations_email"), "invitations", ["email"], unique=False)
    op.create_table(
        "memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("owner", "admin", "agent", "viewer", name="role", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("node_codes", json_type, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "org_id", name="uq_memberships_user_org"),
    )
    op.create_index(op.f("ix_memberships_org_id"), "memberships", ["org_id"], unique=False)
    op.create_table(
        "org_links",
        sa.Column("forwarder_id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["client_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["forwarder_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("forwarder_id", "client_id"),
    )
    op.create_index(op.f("ix_org_links_client_id"), "org_links", ["client_id"], unique=False)
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("device_name", sa.String(length=256), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)
    op.create_table(
        "shipments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ref", sa.String(length=64), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=False),
        sa.Column("container_no", sa.String(length=32), nullable=True),
        sa.Column("container_type", sa.String(length=32), nullable=True),
        sa.Column("route", json_type, nullable=False),
        sa.Column("planned_departure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cargo", sa.Text(), nullable=True),
        sa.Column("cargo_en", sa.Text(), nullable=True),
        sa.Column("cargo_manifest", json_type, nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ref"),
    )
    op.create_index(op.f("ix_shipments_org_id"), "shipments", ["org_id"], unique=False)
    op.create_table(
        "shipment_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shipment_id", sa.Integer(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "arrived",
                "departed",
                "held",
                "released",
                name="checkpointeventkind",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("node_code", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hold_code", sa.String(length=32), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("vessel", sa.String(length=128), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("supersedes_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supersedes_id"], ["shipment_events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_shipment_events_shipment_at",
        "shipment_events",
        ["shipment_id", "occurred_at"],
        unique=False,
    )
    op.create_table(
        "shipment_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shipment_id", sa.Integer(), nullable=False),
        sa.Column("changed_by", sa.Integer(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("before", json_type, nullable=False),
        sa.Column("after", json_type, nullable=False),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_shipment_revisions_shipment_id"),
        "shipment_revisions",
        ["shipment_id"],
        unique=False,
    )
    op.create_table(
        "shipment_shares",
        sa.Column("shipment_id", sa.Integer(), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("shipment_id", "org_id"),
    )
    op.create_index(op.f("ix_shipment_shares_org_id"), "shipment_shares", ["org_id"], unique=False)
    op.create_table(
        "subscriptions",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("shipment_id", sa.Integer(), nullable=False),
        sa.Column("push", sa.Boolean(), nullable=False),
        sa.Column("email", sa.Boolean(), nullable=False),
        sa.Column("muted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "shipment_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("subscriptions")
    op.drop_index(op.f("ix_shipment_shares_org_id"), table_name="shipment_shares")
    op.drop_table("shipment_shares")
    op.drop_index(op.f("ix_shipment_revisions_shipment_id"), table_name="shipment_revisions")
    op.drop_table("shipment_revisions")
    op.drop_index("ix_shipment_events_shipment_at", table_name="shipment_events")
    op.drop_table("shipment_events")
    op.drop_index(op.f("ix_shipments_org_id"), table_name="shipments")
    op.drop_table("shipments")
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_index(op.f("ix_org_links_client_id"), table_name="org_links")
    op.drop_table("org_links")
    op.drop_index(op.f("ix_memberships_org_id"), table_name="memberships")
    op.drop_table("memberships")
    op.drop_index(op.f("ix_invitations_email"), table_name="invitations")
    op.drop_index(op.f("ix_invitations_org_id"), table_name="invitations")
    op.drop_table("invitations")
    op.drop_index(op.f("ix_devices_user_id"), table_name="devices")
    op.drop_table("devices")
    op.drop_table("audit_log")
    op.drop_table("users")
    op.drop_table("organizations")
    op.drop_index("ix_login_codes_ip_created", table_name="login_codes")
    op.drop_index("ix_login_codes_email_created", table_name="login_codes")
    op.drop_table("login_codes")
