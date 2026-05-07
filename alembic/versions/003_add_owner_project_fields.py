"""Add owner project fields

Revision ID: 003
Revises: 84adf20afe0e
Create Date: 2026-05-07 19:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '003'
down_revision = '84adf20afe0e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'project_config',
        sa.Column('owner_project', sa.String(length=200), nullable=True, comment='所属项目名称')
    )
    op.create_index('ix_project_config_owner_project', 'project_config', ['owner_project'])

    op.add_column(
        'subscription_config',
        sa.Column('owner_project', sa.String(length=200), nullable=True, comment='所属项目名称')
    )
    op.create_index('ix_subscription_config_owner_project', 'subscription_config', ['owner_project'])


def downgrade() -> None:
    op.drop_index('ix_subscription_config_owner_project', table_name='subscription_config')
    op.drop_column('subscription_config', 'owner_project')
    op.drop_index('ix_project_config_owner_project', table_name='project_config')
    op.drop_column('project_config', 'owner_project')
