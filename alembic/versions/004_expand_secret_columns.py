"""Expand secret columns for encrypted values

Revision ID: 004
Revises: 003
Create Date: 2026-05-17 16:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('project_config') as batch_op:
        batch_op.alter_column(
            'api_key',
            existing_type=sa.String(length=500),
            type_=sa.Text(),
            existing_nullable=False,
        )

    inspector = sa.inspect(op.get_bind())
    if inspector.has_table('email_config'):
        with op.batch_alter_table('email_config') as batch_op:
            batch_op.alter_column(
                'password',
                existing_type=sa.String(length=500),
                type_=sa.Text(),
                existing_nullable=False,
            )


def downgrade() -> None:
    with op.batch_alter_table('project_config') as batch_op:
        batch_op.alter_column(
            'api_key',
            existing_type=sa.Text(),
            type_=sa.String(length=500),
            existing_nullable=False,
        )

    inspector = sa.inspect(op.get_bind())
    if inspector.has_table('email_config'):
        with op.batch_alter_table('email_config') as batch_op:
            batch_op.alter_column(
                'password',
                existing_type=sa.Text(),
                type_=sa.String(length=500),
                existing_nullable=False,
            )
