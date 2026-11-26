"""jobs: target switch and a short summary for the task list

Revision ID: 9d2f6b18e4a7
Revises: 5e0b7a1c3d92
Create Date: 2026-11-26 10:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '9d2f6b18e4a7'
down_revision: str | None = '5e0b7a1c3d92'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('jobs') as batch:
        batch.add_column(sa.Column('device_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('summary', sa.String(length=255), nullable=False, server_default=''))
        batch.create_index(batch.f('ix_jobs_device_id'), ['device_id'])
        batch.create_foreign_key(
            batch.f('fk_jobs_device_id_devices'),
            'devices',
            ['device_id'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    with op.batch_alter_table('jobs') as batch:
        batch.drop_constraint(batch.f('fk_jobs_device_id_devices'), type_='foreignkey')
        batch.drop_index(batch.f('ix_jobs_device_id'))
        batch.drop_column('summary')
        batch.drop_column('device_id')
