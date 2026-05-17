"""drop due_date from tasks

Revision ID: a1b2c3d4e5f6
Revises: bdbac2de587a
Create Date: 2026-05-17

"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = 'bdbac2de587a'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.drop_column('due_date')


def downgrade():
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('due_date', sa.Date(), nullable=True))
