"""allow shared project_ids across users

Revision ID: b4c9d8e2f3a5
Revises: a3b8c7d9e1f2
Create Date: 2026-02-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b4c9d8e2f3a5'
down_revision: Union[str, Sequence[str], None] = 'a3b8c7d9e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Change the projects table so that multiple users can share the same
    project_id value.  A new auto-increment `id` column becomes the PK,
    and (project_id, user_id) becomes a unique constraint.

    Foreign keys in assets and chunks are updated to reference projects.id.
    Existing data is preserved: for every existing row the new `id` column
    is set equal to the old `project_id` value so FK values remain valid.
    """

    # --- Step 1: Add new `id` column (nullable for now) ---
    op.add_column('projects', sa.Column('id', sa.Integer(), nullable=True))

    # Populate `id` from current project_id for existing rows
    op.execute("UPDATE projects SET id = project_id")

    # --- Step 2: Drop foreign keys that reference projects.project_id ---
    # Assets FK
    op.drop_constraint('assets_asset_project_id_fkey', 'assets', type_='foreignkey')
    # Chunks FK
    op.drop_constraint('chunks_chunk_project_id_fkey', 'chunks', type_='foreignkey')

    # --- Step 3: Drop old primary key on project_id ---
    op.drop_constraint('projects_pkey', 'projects', type_='primary')

    # --- Step 4: Make `id` NOT NULL and set as new PK ---
    op.alter_column('projects', 'id', nullable=False)

    # Create a sequence for future auto-increment on `id`
    op.execute("CREATE SEQUENCE IF NOT EXISTS projects_id_seq OWNED BY projects.id")
    op.execute("SELECT setval('projects_id_seq', GREATEST(COALESCE((SELECT MAX(id) FROM projects), 0), 1))")
    op.execute("ALTER TABLE projects ALTER COLUMN id SET DEFAULT nextval('projects_id_seq')")

    op.create_primary_key('projects_pkey', 'projects', ['id'])

    # --- Step 5: Remove autoincrement default from project_id ---
    # Drop the old sequence if it exists (was tied to autoincrement on project_id)
    op.execute("ALTER TABLE projects ALTER COLUMN project_id DROP DEFAULT")
    op.execute("DROP SEQUENCE IF EXISTS projects_project_id_seq")

    # --- Step 6: Add unique constraint on (project_id, user_id) ---
    op.create_unique_constraint('uq_project_user', 'projects', ['project_id', 'user_id'])

    # --- Step 7: Add index on project_id for faster lookups ---
    op.create_index('ix_project_project_id', 'projects', ['project_id'])

    # --- Step 8: Recreate foreign keys pointing to projects.id ---
    op.create_foreign_key(
        'assets_asset_project_id_fkey', 'assets', 'projects',
        ['asset_project_id'], ['id']
    )
    op.create_foreign_key(
        'chunks_chunk_project_id_fkey', 'chunks', 'projects',
        ['chunk_project_id'], ['id']
    )


def downgrade() -> None:
    """Reverse the migration: restore project_id as the sole PK."""

    # Drop new FKs
    op.drop_constraint('chunks_chunk_project_id_fkey', 'chunks', type_='foreignkey')
    op.drop_constraint('assets_asset_project_id_fkey', 'assets', type_='foreignkey')

    # Drop index and unique constraint
    op.drop_index('ix_project_project_id', table_name='projects')
    op.drop_constraint('uq_project_user', 'projects', type_='unique')

    # Drop new PK
    op.drop_constraint('projects_pkey', 'projects', type_='primary')

    # Restore project_id as PK with autoincrement
    op.execute("CREATE SEQUENCE IF NOT EXISTS projects_project_id_seq OWNED BY projects.project_id")
    op.execute("SELECT setval('projects_project_id_seq', COALESCE((SELECT MAX(project_id) FROM projects), 0))")
    op.execute("ALTER TABLE projects ALTER COLUMN project_id SET DEFAULT nextval('projects_project_id_seq')")
    op.create_primary_key('projects_pkey', 'projects', ['project_id'])

    # Drop id column and its sequence
    op.execute("DROP SEQUENCE IF EXISTS projects_id_seq")
    op.drop_column('projects', 'id')

    # Recreate original FKs pointing to projects.project_id
    op.create_foreign_key(
        'assets_asset_project_id_fkey', 'assets', 'projects',
        ['asset_project_id'], ['project_id']
    )
    op.create_foreign_key(
        'chunks_chunk_project_id_fkey', 'chunks', 'projects',
        ['chunk_project_id'], ['project_id']
    )
