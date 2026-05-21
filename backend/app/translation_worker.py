import asyncio
import logging
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from . import models
from .config import Settings
from .database import SessionLocal
from .translation import _images_for_scope
from .translation_client import TranslationClient

worker_logger = logging.getLogger("mangamanager.translation")


class TranslationClientProtocol(Protocol):
    async def submit_proxy_translate_async(
        self,
        *,
        file_path: Path,
        source_language: str,
        target_language: str,
        model_id: str,
        font_style: str,
        image_id: str,
        original_asset_id: str = "",
        page_url: str = ""
    ) -> dict[str, Any]:
        ...

    async def wait_proxy_translate_async_result(
        self,
        *,
        plugin_id: str,
        timeout_seconds: float = 900.0,
        poll_interval_seconds: float = 1.5
    ) -> dict[str, Any]:
        ...

    async def download_file(self, url: str) -> tuple[bytes, str]:
        ...


@dataclass(frozen=True)
class TranslationWorkerOptions:
    user_id: str = ""
    email: str = ""
    access_token: str = ""
    raw_cookie: str = ""
    base_url: str = ""
    proxy_base: str = ""
    concurrency: int = 3
    poll_interval_seconds: float = 1.5
    timeout_seconds: float = 900.0


def options_from_payload(payload: Any, settings: Settings) -> TranslationWorkerOptions:
    return TranslationWorkerOptions(
        user_id=(getattr(payload, "user_id", "") or settings.translation_user_id).strip(),
        email=(getattr(payload, "email", "") or settings.translation_email).strip(),
        access_token=(getattr(payload, "access_token", "") or settings.translation_access_token).strip(),
        raw_cookie=(getattr(payload, "raw_cookie", "") or "").strip(),
        base_url=(getattr(payload, "base_url", "") or settings.translation_base_url).strip(),
        proxy_base=(getattr(payload, "proxy_base", "") or settings.translation_proxy_base).strip(),
        concurrency=max(1, min(16, int(getattr(payload, "concurrency", 3) or 3)))
    )


async def run_translation_task(
    task_id: str,
    settings: Settings,
    options: TranslationWorkerOptions | None = None,
    client: TranslationClientProtocol | None = None,
    db: Session | None = None
) -> models.TranslationTask:
    owns_db = db is None
    session = db or SessionLocal()
    try:
        return await _run_translation_task(session, task_id, settings, options or TranslationWorkerOptions(), client)
    finally:
        if owns_db:
            session.close()


async def _run_translation_task(
    db: Session,
    task_id: str,
    settings: Settings,
    options: TranslationWorkerOptions,
    client: TranslationClientProtocol | None
) -> models.TranslationTask:
    task = db.get(models.TranslationTask, task_id)
    if not task:
        raise ValueError("translation task not found")

    images = _images_for_scope(db, task.scope_type, task.scope_id)
    versions = _versions_for_images(db, images, task.target_language)
    _mark_task_processing(task, versions)
    task.total = len(images)
    db.commit()

    try:
        if not images:
            task.status = models.TaskStatus.completed
            db.commit()
            db.refresh(task)
            return task
        if not options.user_id:
            raise ValueError("translation user_id is required")

        active_client = client or TranslationClient(
            options.base_url or settings.translation_base_url,
            options.access_token,
            options.proxy_base or settings.translation_proxy_base,
            options.email,
            options.user_id,
            options.raw_cookie
        )
        def handle_result(image: models.MangaImage, result: dict[str, Any] | Exception) -> None:
            version = versions[image.id]
            if isinstance(result, Exception):
                _mark_version_failed(version, str(result))
                worker_logger.error("translation image failed task_id=%s image_id=%s error=%s", task.id, image.id, result)
            else:
                try:
                    _save_translated_image(settings, task, image, version, result["translated_url"], result["content"], result["content_type"])
                except Exception as exc:
                    _mark_version_failed(version, str(exc))
                    worker_logger.exception("save translated image failed task_id=%s image_id=%s", task.id, image.id)
            _update_task_progress(task, versions)
            db.commit()

        await _translate_images_async(task, images, active_client, options, on_result=handle_result)
    except Exception as exc:
        _mark_task_failed(task, versions.values(), str(exc))
        _finish_task_counts(task, versions)
        db.commit()
        db.refresh(task)
        return task

    _finish_task_counts(task, versions)
    db.commit()
    db.refresh(task)
    return task


def run_translation_task_sync(task_id: str, settings: Settings, options: TranslationWorkerOptions | None = None) -> None:
    asyncio.run(run_translation_task(task_id, settings, options))


async def _translate_images_async(
    task: models.TranslationTask,
    images: list[models.MangaImage],
    client: TranslationClientProtocol,
    options: TranslationWorkerOptions,
    on_result: Any | None = None
) -> list[tuple[models.MangaImage, dict[str, Any] | Exception]]:
    semaphore = asyncio.Semaphore(options.concurrency)

    async def translate_one(image: models.MangaImage) -> dict[str, Any]:
        async with semaphore:
            _record_processing_stage(task.id, image.id, task.target_language, f"submitting image {image.page_index}")
            submitted = await client.submit_proxy_translate_async(
                file_path=Path(image.source_path),
                source_language=task.source_language,
                target_language=task.target_language,
                model_id=task.model_id,
                font_style=task.font_id,
                image_id=image.id,
                original_asset_id=image.id,
                page_url=""
            )
            plugin_id = str(submitted.get("plugin_id") or "")
            _record_processing_stage(task.id, image.id, task.target_language, f"submitted plugin_id={plugin_id}")
            status = submitted
            if not status.get("translated_url"):
                _record_processing_stage(task.id, image.id, task.target_language, f"waiting plugin_id={plugin_id}")
                status = await client.wait_proxy_translate_async_result(
                    plugin_id=plugin_id,
                    timeout_seconds=options.timeout_seconds,
                    poll_interval_seconds=options.poll_interval_seconds
                )
            translated_url = str(status.get("translated_url") or "").strip()
            if not translated_url:
                raise ValueError("translated_url missing after async translation")
            _record_processing_stage(task.id, image.id, task.target_language, f"downloading result plugin_id={plugin_id}")
            content, content_type = await client.download_file(translated_url)
            return {"translated_url": translated_url, "content": content, "content_type": content_type}

    async def run_one(image: models.MangaImage) -> tuple[models.MangaImage, dict[str, Any] | Exception]:
        try:
            return image, await translate_one(image)
        except Exception as exc:
            return image, exc

    tasks = [asyncio.create_task(run_one(image)) for image in images]
    results: list[tuple[models.MangaImage, dict[str, Any] | Exception]] = []
    for completed in asyncio.as_completed(tasks):
        image, result = await completed
        results.append((image, result))
        if on_result:
            on_result(image, result)
    return results


def _versions_for_images(db: Session, images: list[models.MangaImage], language: str) -> dict[str, models.ImageVersion]:
    versions: dict[str, models.ImageVersion] = {}
    for image in images:
        version = (
            db.query(models.ImageVersion)
            .filter(models.ImageVersion.image_id == image.id, models.ImageVersion.language == language)
            .one_or_none()
        )
        if not version:
            version = models.ImageVersion(image_id=image.id, language=language)
            db.add(version)
        versions[image.id] = version
    return versions


def _mark_task_processing(task: models.TranslationTask, versions: dict[str, models.ImageVersion]) -> None:
    task.completed = 0
    task.failed = 0
    task.error = ""
    task.status = models.TaskStatus.processing
    for version in versions.values():
        version.status = models.VersionStatus.processing
        version.error = ""


def _record_processing_stage(task_id: str, image_id: str, language: str, message: str) -> None:
    worker_logger.info("translation stage task_id=%s image_id=%s %s", task_id, image_id, message)
    db = SessionLocal()
    try:
        task = db.get(models.TranslationTask, task_id)
        version = (
            db.query(models.ImageVersion)
            .filter(models.ImageVersion.image_id == image_id, models.ImageVersion.language == language)
            .one_or_none()
        )
        if task and task.status == models.TaskStatus.processing:
            task.error = message[:4000]
        if version and version.status == models.VersionStatus.processing:
            version.error = message[:4000]
        db.commit()
    finally:
        db.close()


def _save_translated_image(
    settings: Settings,
    task: models.TranslationTask,
    image: models.MangaImage,
    version: models.ImageVersion,
    translated_url: str,
    content: bytes,
    content_type: str
) -> None:
    destination = _translated_destination(settings, image, task.target_language, translated_url, content_type)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    version.status = models.VersionStatus.completed
    version.file_path = str(destination)
    version.translated_url = translated_url
    version.error = ""


def _translated_destination(settings: Settings, image: models.MangaImage, language: str, url: str, content_type: str) -> Path:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        suffix = mimetypes.guess_extension(content_type.split(";")[0].strip()) or Path(image.source_path).suffix or ".png"
    if suffix == ".jpeg":
        suffix = ".jpg"
    return settings.library_dir / image.chapter.manga_id / image.chapter_id / "translations" / language / f"{image.id}{suffix}"


def _mark_version_failed(version: models.ImageVersion, error: str) -> None:
    version.status = models.VersionStatus.failed
    version.error = error[:4000]


def _mark_task_failed(task: models.TranslationTask, versions: Any, error: str) -> None:
    task.status = models.TaskStatus.failed
    task.error = error[:4000]
    for version in versions:
        if version.status != models.VersionStatus.completed:
            _mark_version_failed(version, error)


def _finish_task_counts(task: models.TranslationTask, versions: dict[str, models.ImageVersion]) -> None:
    task.completed = sum(1 for version in versions.values() if version.status == models.VersionStatus.completed)
    task.failed = sum(1 for version in versions.values() if version.status == models.VersionStatus.failed)
    task.status = models.TaskStatus.completed if task.failed == 0 else models.TaskStatus.failed
    task.error = "" if task.failed == 0 else f"{task.failed} image(s) failed"


def _update_task_progress(task: models.TranslationTask, versions: dict[str, models.ImageVersion]) -> None:
    task.completed = sum(1 for version in versions.values() if version.status == models.VersionStatus.completed)
    task.failed = sum(1 for version in versions.values() if version.status == models.VersionStatus.failed)
    if task.completed + task.failed < task.total:
        task.status = models.TaskStatus.processing
        task.error = ""
