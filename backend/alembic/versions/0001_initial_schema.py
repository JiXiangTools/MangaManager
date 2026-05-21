"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


version_status = postgresql.ENUM("missing", "queued", "processing", "completed", "failed", name="versionstatus")
task_status = postgresql.ENUM("queued", "processing", "completed", "failed", name="taskstatus")
version_status_column = postgresql.ENUM(
    "missing", "queued", "processing", "completed", "failed", name="versionstatus", create_type=False
)
task_status_column = postgresql.ENUM("queued", "processing", "completed", "failed", name="taskstatus", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    version_status.create(bind, checkfirst=True)
    task_status.create(bind, checkfirst=True)

    op.create_table(
        "manga",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("homepage", sa.String(length=1000), nullable=False),
        sa.Column("default_language", sa.String(length=16), nullable=False),
        sa.Column("cover_image_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id")
    )
    op.create_table(
        "chapters",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("manga_id", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("number", sa.String(length=64), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["manga_id"], ["manga.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id")
    )
    op.create_index(op.f("ix_chapters_manga_id"), "chapters", ["manga_id"], unique=False)
    op.create_table(
        "images",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("chapter_id", sa.String(length=32), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("page_index", sa.Integer(), nullable=False),
        sa.Column("source_path", sa.String(length=1000), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id")
    )
    op.create_index(op.f("ix_images_chapter_id"), "images", ["chapter_id"], unique=False)
    op.create_table(
        "translation_tasks",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("scope_id", sa.String(length=32), nullable=False),
        sa.Column("source_language", sa.String(length=16), nullable=False),
        sa.Column("target_language", sa.String(length=16), nullable=False),
        sa.Column("model_id", sa.String(length=100), nullable=False),
        sa.Column("font_id", sa.String(length=100), nullable=False),
        sa.Column("status", task_status_column, nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("completed", sa.Integer(), nullable=False),
        sa.Column("failed", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id")
    )
    op.create_table(
        "export_tasks",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("scope_id", sa.String(length=32), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("image_format", sa.String(length=10), nullable=False),
        sa.Column("status", task_status_column, nullable=False),
        sa.Column("file_path", sa.String(length=1000), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id")
    )
    op.create_table(
        "image_versions",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("image_id", sa.String(length=32), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("status", version_status_column, nullable=False),
        sa.Column("file_path", sa.String(length=1000), nullable=False),
        sa.Column("translated_url", sa.String(length=1000), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("source_language", sa.String(length=16), nullable=False),
        sa.Column("target_language", sa.String(length=16), nullable=False),
        sa.Column("model_id", sa.String(length=100), nullable=False),
        sa.Column("font_id", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("image_id", "language", name="uq_image_version_language")
    )
    op.create_index(op.f("ix_image_versions_image_id"), "image_versions", ["image_id"], unique=False)
    op.create_index(op.f("ix_image_versions_language"), "image_versions", ["language"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_image_versions_language"), table_name="image_versions")
    op.drop_index(op.f("ix_image_versions_image_id"), table_name="image_versions")
    op.drop_table("image_versions")
    op.drop_table("export_tasks")
    op.drop_table("translation_tasks")
    op.drop_index(op.f("ix_images_chapter_id"), table_name="images")
    op.drop_table("images")
    op.drop_index(op.f("ix_chapters_manga_id"), table_name="chapters")
    op.drop_table("chapters")
    op.drop_table("manga")
    task_status.drop(op.get_bind(), checkfirst=True)
    version_status.drop(op.get_bind(), checkfirst=True)
