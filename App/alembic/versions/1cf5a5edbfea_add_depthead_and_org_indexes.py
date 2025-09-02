"""Add depthead and org indexes

Revision ID: 1cf5a5edbfea
Revises: 
Create Date: 2025-06-17 09:48:10.725062

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '1cf5a5edbfea'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """
    Create indexes to speed up Dept→Head and Employee lookups.
    """
    op.create_index(
        'ix_dept_head_lookup',
        'departments',
        ['department_head_id'],
    )
    op.create_index(
        'ix_dept_org',
        'departments',
        ['organization_id', 'id'],
        unique=False,
    )
    op.create_index(
        'ix_emp_org_head',
        'employees',
        ['organization_id', 'id'],
        unique=False,
    )


def downgrade() -> None:
    """
    Drop the indexes added in upgrade().
    """
    op.drop_index('ix_emp_org_head', table_name='employees')
    op.drop_index('ix_dept_org', table_name='departments')
    op.drop_index('ix_dept_head_lookup', table_name='departments')

