"""device api login: own API user and password per switch

Revision ID: c4d81e2a9f37
Revises: a7c3e91d4b20
Create Date: 2026-11-17 10:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'c4d81e2a9f37'
down_revision: str | None = 'a7c3e91d4b20'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('devices') as batch:
        batch.add_column(sa.Column('api_username', sa.String(length=100), nullable=True))
        batch.add_column(sa.Column('api_password_encrypted', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('devices') as batch:
        batch.drop_column('api_password_encrypted')
        batch.drop_column('api_username')
