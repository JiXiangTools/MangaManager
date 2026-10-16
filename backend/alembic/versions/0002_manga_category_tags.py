"""add manga category and tags

Revision ID: 0002_manga_category_tags
Revises: 0001_initial_schema
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_manga_category_tags"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("manga", sa.Column("category", sa.String(length=255), nullable=False, server_default=""))
    op.add_column("manga", sa.Column("tags", sa.Text(), nullable=False, server_default=""))
    op.alter_column("manga", "category", server_default=None)
    op.alter_column("manga", "tags", server_default=None)


def downgrade() -> None:
    op.drop_column("manga", "tags")
    op.drop_column("manga", "category")
