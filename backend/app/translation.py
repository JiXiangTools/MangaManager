from sqlalchemy.orm import Session

from . import models
from .schemas import TranslateRequest


def _images_for_scope(db: Session, scope_type: str, scope_id: str) -> list[models.MangaImage]:
    if scope_type == "image":
        image = db.get(models.MangaImage, scope_id)
        return [image] if image else []
    if scope_type == "chapter":
        return db.query(models.MangaImage).filter(models.MangaImage.chapter_id == scope_id).order_by(models.MangaImage.page_index).all()
    if scope_type == "manga":
        return (
            db.query(models.MangaImage)
            .join(models.Chapter, models.MangaImage.chapter_id == models.Chapter.id)
            .filter(models.Chapter.manga_id == scope_id)
            .order_by(models.Chapter.sort_order, models.MangaImage.page_index)
            .all()
        )
    return []


def create_translation_task(db: Session, scope_type: str, scope_id: str, payload: TranslateRequest) -> models.TranslationTask:
    images = _images_for_scope(db, scope_type, scope_id)
    task = models.TranslationTask(
        scope_type=scope_type,
        scope_id=scope_id,
        source_language=payload.source_language,
        target_language=payload.target_language,
        model_id=payload.model_id,
        font_id=payload.font_id,
        status=models.TaskStatus.queued,
        total=len(images)
    )
    db.add(task)
    for image in images:
        version = (
            db.query(models.ImageVersion)
            .filter(models.ImageVersion.image_id == image.id, models.ImageVersion.language == payload.target_language)
            .one_or_none()
        )
        if not version:
            version = models.ImageVersion(image_id=image.id, language=payload.target_language)
            db.add(version)
        version.status = models.VersionStatus.queued
        version.source_language = payload.source_language
        version.target_language = payload.target_language
        version.model_id = payload.model_id
        version.font_id = payload.font_id
    db.commit()
    db.refresh(task)
    return task

