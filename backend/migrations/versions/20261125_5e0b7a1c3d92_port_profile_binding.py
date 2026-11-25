"""port profile binding: ports bound permanently to a port profile

Revision ID: 5e0b7a1c3d92
Revises: c4d81e2a9f37
Create Date: 2026-11-25 10:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '5e0b7a1c3d92'
down_revision: str | None = 'c4d81e2a9f37'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('ports') as batch:
        batch.add_column(sa.Column('port_profile_id', sa.Integer(), nullable=True))
        batch.create_index(batch.f('ix_ports_port_profile_id'), ['port_profile_id'])
        batch.create_foreign_key(
            batch.f('fk_ports_port_profile_id_port_profiles'),
            'port_profiles',
            ['port_profile_id'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    with op.batch_alter_table('ports') as batch:
        batch.drop_constraint(batch.f('fk_ports_port_profile_id_port_profiles'), type_='foreignkey')
        batch.drop_index(batch.f('ix_ports_port_profile_id'))
        batch.drop_column('port_profile_id')
