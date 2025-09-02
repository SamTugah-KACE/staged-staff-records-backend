"""Add partial unique index on active tokens

Revision ID: 2a7d9b3c8e4f
Revises: 1cf5a5edbfea
Create Date: 2025-06-18 10:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '2a7d9b3c8e4f'
down_revision = '1cf5a5edbfea'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        'ix_tokens_user_org',
        'tokens',
        ['user_id', 'organization_id'],
        unique=False,
    )

def downgrade():
    op.drop_index('ix_tokens_user_org', table_name='tokens')
 