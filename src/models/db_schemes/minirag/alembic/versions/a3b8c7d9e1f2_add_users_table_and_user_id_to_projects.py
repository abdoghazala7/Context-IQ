"""add users table and user_id to projects

Revision ID: a3b8c7d9e1f2
Revises: 06a1f14610c7
Create Date: 2026-02-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a3b8c7d9e1f2'
down_revision: Union[str, Sequence[str], None] = '06a1f14610c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    1. Create the 'users' table for authentication and ownership.
    2. Insert a default user so existing projects can be migrated.
    3. Add 'user_id' column to 'projects' referencing 'users.user_id'.
    4. Assign all existing projects to the default user.
    5. Make 'user_id' NOT NULL after migration.
    """
    # Step 1: Create users table
    op.create_table(
        'users',
        sa.Column('user_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_api_key', sa.String(), nullable=False),
        sa.Column('user_name', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('user_id'),
        sa.UniqueConstraint('user_api_key')
    )
    op.create_index('ix_users_api_key', 'users', ['user_api_key'], unique=True)

    # Step 2: Insert a default user for existing data migration
    op.execute(
        "INSERT INTO users (user_api_key, user_name, is_active) "
        "VALUES ('default-migration-key-change-me', 'Default Migration User', true)"
    )

    # Step 3: Add user_id column as NULLABLE first (so existing rows don't break)
    op.add_column('projects', sa.Column('user_id', sa.Integer(), nullable=True))

    # Step 4: Assign all existing projects to the default user (user_id = 1)
    op.execute("UPDATE projects SET user_id = 1 WHERE user_id IS NULL")

    # Step 5: Make user_id NOT NULL now that all rows have a value
    op.alter_column('projects', 'user_id', nullable=False)

    # Step 6: Add foreign key constraint and index
    op.create_foreign_key(
        'fk_projects_user_id', 'projects', 'users',
        ['user_id'], ['user_id']
    )
    op.create_index('ix_project_user_id', 'projects', ['user_id'])


def downgrade() -> None:
    """Reverse: remove user_id from projects, drop users table."""
    op.drop_index('ix_project_user_id', table_name='projects')
    op.drop_constraint('fk_projects_user_id', 'projects', type_='foreignkey')
    op.drop_column('projects', 'user_id')
    op.drop_index('ix_users_api_key', table_name='users')
    op.drop_table('users')
