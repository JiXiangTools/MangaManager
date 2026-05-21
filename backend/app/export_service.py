import shutil
import zipfile
from pathlib import Path

from sqlalchemy.orm import Session

from . import models
from .config import Settings
from .schemas import ExportRequest
from .storage import IMAGE_FORMATS, convert_image


def _chapters_for_scope(db: Session, scope_type: str, scope_id: str) -> list[models.Chapter]:
    if scope_type == "chapter":
        chapter = db.get(models.Chapter, scope_id)
        return [chapter] if chapter else []
    if scope_type == "manga":
        return db.query(models.Chapter).filter(models.Chapter.manga_id == scope_id).order_by(models.Chapter.sort_order).all()
    return []


def _source_for_language(db: Session, image: models.MangaImage, language: str, skip_missing: bool) -> Path | None:
    version = (
        db.query(models.ImageVersion)
        .filter(models.ImageVersion.image_id == image.id, models.ImageVersion.language == language)
        .one_or_none()
    )
    if version and version.status == models.VersionStatus.completed and version.file_path:
        return Path(version.file_path)
    if skip_missing:
        return None
    return Path(image.source_path)


def create_export(db: Session, settings: Settings, scope_type: str, scope_id: str, payload: ExportRequest) -> models.ExportTask:
    task = models.ExportTask(scope_type=scope_type, scope_id=scope_id, language=payload.language, image_format=payload.image_format)
    db.add(task)
    db.commit()
    db.refresh(task)

    export_root = settings.exports_dir / task.id
    work_root = export_root / "work"
    zip_path = export_root / f"{scope_type}-{scope_id}-{payload.language}.{task.image_format}.zip"
    try:
        if payload.image_format not in IMAGE_FORMATS:
            raise ValueError("unsupported image format")
        suffix = IMAGE_FORMATS[payload.image_format][1]
        chapters = _chapters_for_scope(db, scope_type, scope_id)
        for chapter_index, chapter in enumerate(chapters, start=1):
            for image in chapter.images:
                source = _source_for_language(db, image, payload.language, payload.skip_missing)
                if not source or not source.exists():
                    continue
                safe_chapter = f"{chapter_index:04d}-{chapter.title}".replace("/", "_").replace("\\", "_")
                dest = work_root / safe_chapter / f"{image.page_index:04d}{suffix}"
                convert_image(source, dest, payload.image_format)
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for file_path in work_root.rglob("*"):
                if file_path.is_file():
                    archive.write(file_path, file_path.relative_to(work_root))
        shutil.rmtree(work_root, ignore_errors=True)
        task.status = models.TaskStatus.completed
        task.file_path = str(zip_path)
    except Exception as exc:
        task.status = models.TaskStatus.failed
        task.error = str(exc)
    db.commit()
    db.refresh(task)
    return task

