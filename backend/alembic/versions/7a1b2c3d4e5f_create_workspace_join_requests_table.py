"""create_workspace_join_requests_table

Revision ID: 7a1b2c3d4e5f
Revises: 52b31ff9bb51
Create Date: 2026-10-25 15:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a1b2c3d4e5f'
down_revision: Union[str, None] = '52b31ff9bb51'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'workspace_join_requests',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('company_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('reviewed_by_id', sa.String(length=36), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewed_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_workspace_join_requests_id'), 'workspace_join_requests', ['id'], unique=False)
    op.create_index(op.f('ix_workspace_join_requests_company_id'), 'workspace_join_requests', ['company_id'], unique=False)
    op.create_index(op.f('ix_workspace_join_requests_user_id'), 'workspace_join_requests', ['user_id'], unique=False)
    op.create_index(op.f('ix_workspace_join_requests_email'), 'workspace_join_requests', ['email'], unique=False)
    op.create_index(op.f('ix_workspace_join_requests_status'), 'workspace_join_requests', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_workspace_join_requests_status'), table_name='workspace_join_requests')
    op.drop_index(op.f('ix_workspace_join_requests_email'), table_name='workspace_join_requests')
    op.drop_index(op.f('ix_workspace_join_requests_user_id'), table_name='workspace_join_requests')
    op.drop_index(op.f('ix_workspace_join_requests_company_id'), table_name='workspace_join_requests')
    op.drop_index(op.f('ix_workspace_join_requests_id'), table_name='workspace_join_requests')
    op.drop_table('workspace_join_requests')
