import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .constants import DEFAULT_LANGUAGE
from .database import Base


def new_id() -> str:
    return uuid.uuid4().hex


class VersionStatus(str, enum.Enum):
    missing = "missing"
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class TaskStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class Manga(Base):
    __tablename__ = "manga"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    homepage: Mapped[str] = mapped_column(String(1000), default="")
    default_language: Mapped[str] = mapped_column(String(16), default=DEFAULT_LANGUAGE)
    cover_image_id: Mapped[str] = mapped_column(String(32), default="")
    category: Mapped[str] = mapped_column(String(255), default="")
    tags: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    chapters: Mapped[list["Chapter"]] = relationship(back_populates="manga", cascade="all, delete-orphan", order_by="Chapter.sort_order")


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    manga_id: Mapped[str] = mapped_column(ForeignKey("manga.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    number: Mapped[str] = mapped_column(String(64), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    manga: Mapped[Manga] = relationship(back_populates="chapters")
    images: Mapped[list["MangaImage"]] = relationship(back_populates="chapter", cascade="all, delete-orphan", order_by="MangaImage.page_index")


class MangaImage(Base):
    __tablename__ = "images"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    chapter_id: Mapped[str] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    page_index: Mapped[int] = mapped_column(Integer, default=0)
    source_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), default="application/octet-stream")
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    chapter: Mapped[Chapter] = relationship(back_populates="images")
    versions: Mapped[list["ImageVersion"]] = relationship(back_populates="image", cascade="all, delete-orphan")


class ImageVersion(Base):
    __tablename__ = "image_versions"
    __table_args__ = (UniqueConstraint("image_id", "language", name="uq_image_version_language"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    image_id: Mapped[str] = mapped_column(ForeignKey("images.id", ondelete="CASCADE"), nullable=False, index=True)
    language: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    status: Mapped[VersionStatus] = mapped_column(Enum(VersionStatus), default=VersionStatus.missing)
    file_path: Mapped[str] = mapped_column(String(1000), default="")
    translated_url: Mapped[str] = mapped_column(String(1000), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    source_language: Mapped[str] = mapped_column(String(16), default="")
    target_language: Mapped[str] = mapped_column(String(16), default="")
    model_id: Mapped[str] = mapped_column(String(100), default="")
    font_id: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    image: Mapped[MangaImage] = relationship(back_populates="versions")


class TranslationTask(Base):
    __tablename__ = "translation_tasks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(32), nullable=False)
    source_language: Mapped[str] = mapped_column(String(16), nullable=False)
    target_language: Mapped[str] = mapped_column(String(16), nullable=False)
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)
    font_id: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.queued)
    total: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ExportTask(Base):
    __tablename__ = "export_tasks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    image_format: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.queued)
    file_path: Mapped[str] = mapped_column(String(1000), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
