"""shared SSH key list: drop the "ssh.login" permission from roles

Revision ID: a7c3e91d4b20
Revises: 32727d298e75
Create Date: 2026-11-11 14:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'a7c3e91d4b20'
down_revision: str | None = '32727d298e75'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

roles = sa.table(
    "roles",
    sa.column("id", sa.Integer()),
    sa.column("permissions", sa.JSON()),
    sa.column("builtin", sa.String()),
)


def upgrade() -> None:
    """Every key in the list now goes to every switch; the per-site permission is gone."""
    conn = op.get_bind()
    for role_id, permissions in conn.execute(sa.select(roles.c.id, roles.c.permissions)):
        if permissions and "ssh.login" in permissions:
            kept = [p for p in permissions if p != "ssh.login"]
            conn.execute(roles.update().where(roles.c.id == role_id).values(permissions=kept))


def downgrade() -> None:
    """Built-in administrators get the permission back; custom roles have to be edited."""
    conn = op.get_bind()
    for role_id, permissions in conn.execute(
        sa.select(roles.c.id, roles.c.permissions).where(roles.c.builtin == "admin")
    ):
        conn.execute(
            roles.update()
            .where(roles.c.id == role_id)
            .values(permissions=[*(permissions or []), "ssh.login"])
        )
