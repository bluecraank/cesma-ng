"""roles, ssh key owners, emergency password, device addresses

Revision ID: 22b30a02e5e9
Revises: 294975d0c506
Create Date: 2026-11-09 22:08:08.315097
"""
from collections.abc import Sequence

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = '22b30a02e5e9'
down_revision: str | None = '294975d0c506'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ALL_PERMISSIONS = [
    "devices.manage", "ports.edit", "vlans.manage", "backups.run", "backups.read",
    "backups.restore", "console", "ssh_keys.push", "ssh.login",
]


def upgrade() -> None:
    roles = op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column(
            "permissions",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("builtin", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
        sa.UniqueConstraint("name", name=op.f("uq_roles_name")),
        sa.UniqueConstraint("builtin", name=op.f("uq_roles_builtin")),
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        roles,
        [
            {"id": 1, "name": "Lesen", "description": "Alles ansehen, Abfragen anstoßen",
             "permissions": [], "builtin": "viewer", "created_at": now, "updated_at": now},
            {"id": 2, "name": "Administrator", "description": "Alle Rechte am Standort",
             "permissions": ALL_PERMISSIONS, "builtin": "admin", "created_at": now,
             "updated_at": now},
        ],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("SELECT setval(pg_get_serial_sequence('roles', 'id'), 2)")

    with op.batch_alter_table("user_site_roles") as batch:
        batch.add_column(sa.Column("role_id", sa.Integer(), nullable=True))
    op.execute("UPDATE user_site_roles SET role_id = CASE WHEN role = 'admin' THEN 2 ELSE 1 END")
    with op.batch_alter_table("user_site_roles") as batch:
        batch.alter_column("role_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key(
            op.f("fk_user_site_roles_role_id_roles"), "roles", ["role_id"], ["id"],
            ondelete="RESTRICT",
        )
        batch.drop_column("role")

    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("local_password_hash", sa.String(length=255), nullable=True))

    with op.batch_alter_table("ssh_public_keys") as batch:
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch.create_index(op.f("ix_ssh_public_keys_user_id"), ["user_id"])
        batch.create_foreign_key(
            op.f("fk_ssh_public_keys_user_id_users"), "users", ["user_id"], ["id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("devices") as batch:
        batch.add_column(sa.Column("ip_address", sa.String(length=45), nullable=True))
        batch.add_column(sa.Column("dns_name", sa.String(length=255), nullable=True))
        batch.add_column(
            sa.Column("address_checked_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("devices") as batch:
        batch.drop_column("address_checked_at")
        batch.drop_column("dns_name")
        batch.drop_column("ip_address")
    with op.batch_alter_table("ssh_public_keys") as batch:
        batch.drop_constraint(op.f("fk_ssh_public_keys_user_id_users"), type_="foreignkey")
        batch.drop_index(op.f("ix_ssh_public_keys_user_id"))
        batch.drop_column("user_id")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("local_password_hash")
    with op.batch_alter_table("user_site_roles") as batch:
        batch.add_column(sa.Column("role", sa.String(length=20), nullable=True))
    op.execute(
        "UPDATE user_site_roles SET role = CASE WHEN role_id = 2 THEN 'admin' ELSE 'viewer' END"
    )
    with op.batch_alter_table("user_site_roles") as batch:
        batch.alter_column("role", existing_type=sa.String(length=20), nullable=False)
        batch.drop_constraint(op.f("fk_user_site_roles_role_id_roles"), type_="foreignkey")
        batch.drop_column("role_id")
    op.drop_table("roles")
