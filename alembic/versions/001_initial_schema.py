"""Initial database schema

Revision ID: 001
Revises:
Create Date: 2024-02-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create initial database tables"""

    # Create balance_history table
    op.create_table(
        'balance_history',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('project_id', sa.String(200), nullable=False, index=True, comment='项目唯一标识'),
        sa.Column('project_name', sa.String(200), nullable=False, comment='项目名称'),
        sa.Column('provider', sa.String(50), nullable=False, index=True, comment='Provider 类型'),
        sa.Column('balance', sa.Float(), nullable=False, comment='余额或积分数量'),
        sa.Column('threshold', sa.Float(), comment='告警阈值'),
        sa.Column('currency', sa.String(10), default='USD', comment='货币单位'),
        sa.Column('balance_type', sa.String(20), default='credits', comment='类型: balance/credits'),
        sa.Column('need_alarm', sa.Boolean(), default=False, comment='是否需要告警'),
        sa.Column('timestamp', sa.DateTime(), default=sa.func.now(), index=True, comment='记录时间'),
        comment='余额历史记录表'
    )

    # Create indexes for balance_history
    op.create_index('idx_project_time', 'balance_history', ['project_id', 'timestamp'])
    op.create_index('idx_provider_time', 'balance_history', ['provider', 'timestamp'])

    # Create alert_history table
    op.create_table(
        'alert_history',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('project_id', sa.String(200), nullable=False, index=True, comment='项目唯一标识'),
        sa.Column('project_name', sa.String(200), nullable=False, comment='项目名称'),
        sa.Column('alert_type', sa.String(50), nullable=False, index=True, comment='告警类型'),
        sa.Column('status', sa.String(20), default='sent', comment='发送状态: sent/pending/failed'),
        sa.Column('message', sa.Text(), comment='告警消息'),
        sa.Column('balance_value', sa.Float(), comment='触发告警时的余额'),
        sa.Column('threshold_value', sa.Float(), comment='阈值'),
        sa.Column('timestamp', sa.DateTime(), default=sa.func.now(), index=True, comment='告警时间'),
        comment='告警历史记录表'
    )

    # Create indexes for alert_history
    op.create_index('idx_project_type_time', 'alert_history', ['project_id', 'alert_type', 'timestamp'])

    # Create subscription_history table
    op.create_table(
        'subscription_history',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('subscription_id', sa.String(200), nullable=False, index=True, comment='订阅唯一标识'),
        sa.Column('subscription_name', sa.String(200), nullable=False, comment='订阅名称'),
        sa.Column('cycle_type', sa.String(20), nullable=False, comment='周期类型'),
        sa.Column('days_until_renewal', sa.Integer(), comment='距离续费天数'),
        sa.Column('amount', sa.Float(), default=0, comment='订阅金额'),
        sa.Column('currency', sa.String(10), default='CNY', comment='货币'),
        sa.Column('need_renewal', sa.Boolean(), default=False, comment='是否需要续费'),
        sa.Column('timestamp', sa.DateTime(), default=sa.func.now(), index=True, comment='记录时间'),
        comment='订阅历史记录表'
    )

    # Create indexes for subscription_history
    op.create_index('idx_subscription_time', 'subscription_history', ['subscription_id', 'timestamp'])


def downgrade() -> None:
    """Drop all tables"""
    op.drop_table('subscription_history')
    op.drop_table('alert_history')
    op.drop_table('balance_history')
