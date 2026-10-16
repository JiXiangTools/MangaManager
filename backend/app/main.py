import mimetypes
import os
import re
import shutil
import logging
import secrets
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from . import models, schemas
from .auth import create_session, require_session, verify_password
from .catalogs import fetch_translation_catalogs
from .config import Settings, get_settings
from .constants import DEFAULT_LANGUAGE
from .database import get_db, init_db
from .export_service import create_export
from .storage import ensure_data_dirs, image_extension, image_size, save_upload
from .translation import _images_for_scope, create_translation_task
from .translation_client import TranslationClient
from .translation_worker import options_from_payload, run_translation_task_sync


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = Path(os.getenv("MANGAMANAGER_FRONTEND_DIST", REPO_ROOT / "frontend" / "dist"))
IMPORT_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif"}
reader_logger = logging.getLogger("mangamanager.reader")

app = FastAPI(title="MangaManager API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


@app.on_event("startup")
def on_startup() -> None:
    settings = get_settings()
    ensure_data_dirs(settings)
    init_db()
    app.state.sessions = {}


def web_auth(request: Request) -> None:
    path = request.url.path
    public_paths = {"/api/health", "/api/local/web-auth/login"}
    if path in public_paths:
        return
    if request.headers.get("x-mangamanager-client") == "desktop":
        return
    settings = get_settings()
    desktop_token = request.query_params.get("desktop_token", "")
    client_host = request.client.host if request.client else ""
    if (
        settings.desktop_token
        and desktop_token
        and client_host in {"127.0.0.1", "::1", "localhost"}
        and secrets.compare_digest(desktop_token, settings.desktop_token)
    ):
        return
    require_session(request)


def desktop_auth(request: Request) -> None:
    if request.headers.get("x-mangamanager-client") != "desktop":
        raise HTTPException(status_code=403, detail="desktop client required")


def _cover_path_for_manga(settings: Settings, manga: models.Manga) -> Path | None:
    if not manga.cover_image_id:
        return None
    cover_dir = settings.library_dir / manga.id / "cover"
    if not cover_dir.exists():
        return None
    matches = sorted(cover_dir.glob(f"{manga.cover_image_id}.*"))
    return matches[0] if matches else None


def _is_hidden_path(path: Path) -> bool:
    if any(part.startswith(".") for part in path.parts):
        return True
    if os.name != "nt":
        return False
    try:
        import ctypes

        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        return attrs != -1 and bool(attrs & 0x2)
    except Exception:
        return False


def _is_import_image(path: Path) -> bool:
    return path.is_file() and not _is_hidden_path(path) and path.suffix.lower() in IMPORT_IMAGE_EXTENSIONS


def _safe_sort_key(path: Path) -> str:
    return path.name.casefold()


def _chapter_sort_key(path: Path) -> tuple[int, float, str]:
    match = re.search(r"\d+(?:\.\d+)?", path.name)
    if not match:
        return (1, 0, path.name.casefold())
    try:
        number = float(match.group(0))
    except ValueError:
        number = 0
    return (0, number, path.name.casefold())


def _asset_url(path: str, request: Request, settings: Settings) -> str:
    if request.headers.get("x-mangamanager-client") != "desktop" or not settings.desktop_token:
        return path
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}desktop_token={settings.desktop_token}"


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"ok": "true"}


@app.post("/api/local/web-auth/login")
def login(payload: schemas.PasswordLogin, response: Response, request: Request, settings: Settings = Depends(get_settings)) -> dict[str, bool]:
    if not verify_password(payload.password, settings):
        raise HTTPException(status_code=401, detail="invalid password")
    create_session(response, request.app.state)
    return {"ok": True}


@app.post("/api/translate/auth/cookie", response_model=schemas.TranslationLoginResponse, dependencies=[Depends(web_auth)])
async def translation_cookie_login(
    payload: schemas.TranslationCookieLoginRequest,
    settings: Settings = Depends(get_settings)
) -> dict[str, str]:
    client = TranslationClient(payload.base_url or settings.translation_base_url)
    return await client.login_cookie(payload.raw_cookie)


@app.get("/api/translate/catalogs", dependencies=[Depends(web_auth)])
async def catalogs(settings: Settings = Depends(get_settings)) -> dict:
    return await fetch_translation_catalogs(settings)


@app.post("/api/translate/auth/login", response_model=schemas.TranslationLoginResponse, dependencies=[Depends(web_auth)])
async def translation_login(payload: schemas.TranslationLoginRequest, settings: Settings = Depends(get_settings)) -> dict[str, str]:
    client = TranslationClient(payload.base_url or settings.translation_base_url)
    return await client.login_email(payload.email, payload.password)


@app.get("/api/manga", response_model=list[schemas.MangaOut], dependencies=[Depends(web_auth)])
def list_manga(db: Session = Depends(get_db)) -> list[models.Manga]:
    return db.query(models.Manga).order_by(models.Manga.created_at.desc()).all()


@app.post("/api/manga", response_model=schemas.MangaOut, dependencies=[Depends(web_auth)])
def create_manga(payload: schemas.MangaCreate, db: Session = Depends(get_db)) -> models.Manga:
    manga = models.Manga(**payload.model_dump())
    db.add(manga)
    db.commit()
    db.refresh(manga)
    return manga


@app.post("/api/manga/upload", response_model=schemas.MangaOut, dependencies=[Depends(web_auth)])
async def create_manga_with_cover(
    name: str = Form(...),
    homepage: str = Form(""),
    default_language: str = Form(DEFAULT_LANGUAGE),
    category: str = Form(""),
    tags: str = Form(""),
    cover_image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> models.Manga:
    manga = models.Manga(name=name, homepage=homepage, default_language=default_language, category=category, tags=tags)
    db.add(manga)
    db.flush()
    if cover_image and cover_image.filename:
        cover_id = models.new_id()
        ext = image_extension(cover_image.filename, cover_image.content_type or "")
        destination = settings.library_dir / manga.id / "cover" / f"{cover_id}{ext}"
        await save_upload(cover_image, destination)
        manga.cover_image_id = cover_id
    db.commit()
    db.refresh(manga)
    return manga


@app.post("/api/desktop/import-folder", response_model=schemas.MangaOut, dependencies=[Depends(web_auth), Depends(desktop_auth)])
def import_folder(
    payload: schemas.FolderImportRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> models.Manga:
    root = Path(payload.folder_path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=400, detail="folder not found")
    if _is_hidden_path(root):
        raise HTTPException(status_code=400, detail="hidden folders cannot be imported")

    chapter_dirs = sorted(
        [item for item in root.iterdir() if item.is_dir() and not _is_hidden_path(item)],
        key=_chapter_sort_key
    )
    chapters: list[tuple[Path, list[Path]]] = []
    total_images = 0
    max_images = max(1, min(int(payload.max_images or 5000), 5000))
    for chapter_dir in chapter_dirs:
        images = sorted([item for item in chapter_dir.iterdir() if _is_import_image(item)], key=_safe_sort_key)
        if not images:
            continue
        total_images += len(images)
        if total_images > max_images:
            raise HTTPException(status_code=400, detail=f"too many images: maximum is {max_images}")
        chapters.append((chapter_dir, images))

    if not chapters:
        raise HTTPException(status_code=400, detail="no chapter images found")

    manga = models.Manga(name=root.name, homepage="", default_language=payload.default_language or DEFAULT_LANGUAGE)
    db.add(manga)
    db.flush()

    first_image_path: Path | None = None
    for chapter_index, (chapter_dir, images) in enumerate(chapters, start=1):
        chapter = models.Chapter(
            manga_id=manga.id,
            title=chapter_dir.name,
            number=str(chapter_index),
            sort_order=chapter_index
        )
        db.add(chapter)
        db.flush()
        for page_index, source in enumerate(images, start=1):
            if first_image_path is None:
                first_image_path = source
            content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
            image = models.MangaImage(
                chapter_id=chapter.id,
                original_filename=source.name,
                page_index=page_index,
                source_path="",
                content_type=content_type
            )
            db.add(image)
            db.flush()
            ext = image_extension(source.name, content_type)
            destination = settings.library_dir / manga.id / chapter.id / "source" / f"{image.id}{ext}"
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            image.source_path = str(destination)
            image.width, image.height = image_size(destination)

    if first_image_path:
        cover_id = models.new_id()
        cover_ext = image_extension(first_image_path.name, mimetypes.guess_type(first_image_path.name)[0] or "")
        cover_destination = settings.library_dir / manga.id / "cover" / f"{cover_id}{cover_ext}"
        cover_destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(first_image_path, cover_destination)
        manga.cover_image_id = cover_id

    db.commit()
    db.refresh(manga)
    return manga


@app.get("/api/manga/{manga_id}", response_model=schemas.MangaOut, dependencies=[Depends(web_auth)])
def get_manga(manga_id: str, db: Session = Depends(get_db)) -> models.Manga:
    manga = db.get(models.Manga, manga_id)
    if not manga:
        raise HTTPException(status_code=404, detail="manga not found")
    return manga


@app.patch("/api/manga/{manga_id}", response_model=schemas.MangaOut, dependencies=[Depends(web_auth)])
def update_manga(manga_id: str, payload: schemas.MangaUpdate, db: Session = Depends(get_db)) -> models.Manga:
    manga = db.get(models.Manga, manga_id)
    if not manga:
        raise HTTPException(status_code=404, detail="manga not found")
    values = payload.model_dump(exclude_unset=True)
    for key, value in values.items():
        if value is not None:
            setattr(manga, key, value)
    db.commit()
    db.refresh(manga)
    return manga


@app.delete("/api/manga/{manga_id}", dependencies=[Depends(web_auth)])
def delete_manga(manga_id: str, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict[str, bool]:
    manga = db.get(models.Manga, manga_id)
    if not manga:
        raise HTTPException(status_code=404, detail="manga not found")
    db.delete(manga)
    db.commit()
    shutil.rmtree(settings.library_dir / manga_id, ignore_errors=True)
    return {"ok": True}


@app.get("/api/manga/{manga_id}/cover", dependencies=[Depends(web_auth)])
def get_manga_cover(manga_id: str, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> FileResponse:
    manga = db.get(models.Manga, manga_id)
    if not manga:
        raise HTTPException(status_code=404, detail="manga not found")
    path = _cover_path_for_manga(settings, manga)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="cover not found")
    return FileResponse(path)


@app.post("/api/manga/{manga_id}/cover", response_model=schemas.MangaOut, dependencies=[Depends(web_auth)])
async def upload_manga_cover(
    manga_id: str,
    cover_image: UploadFile = File(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> models.Manga:
    manga = db.get(models.Manga, manga_id)
    if not manga:
        raise HTTPException(status_code=404, detail="manga not found")
    cover_id = models.new_id()
    ext = image_extension(cover_image.filename or "cover", cover_image.content_type or "")
    destination = settings.library_dir / manga.id / "cover" / f"{cover_id}{ext}"
    await save_upload(cover_image, destination)
    manga.cover_image_id = cover_id
    db.commit()
    db.refresh(manga)
    return manga


@app.post("/api/manga/{manga_id}/chapters", response_model=schemas.ChapterOut, dependencies=[Depends(web_auth)])
def create_chapter(manga_id: str, payload: schemas.ChapterCreate, db: Session = Depends(get_db)) -> models.Chapter:
    if not db.get(models.Manga, manga_id):
        raise HTTPException(status_code=404, detail="manga not found")
    chapter = models.Chapter(manga_id=manga_id, **payload.model_dump())
    db.add(chapter)
    db.commit()
    db.refresh(chapter)
    return chapter


@app.patch("/api/chapters/{chapter_id}", response_model=schemas.ChapterOut, dependencies=[Depends(web_auth)])
def update_chapter(chapter_id: str, payload: schemas.ChapterUpdate, db: Session = Depends(get_db)) -> models.Chapter:
    chapter = db.get(models.Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="chapter not found")
    values = payload.model_dump(exclude_unset=True)
    for key, value in values.items():
        if value is not None:
            setattr(chapter, key, value)
    db.commit()
    db.refresh(chapter)
    return chapter


@app.get("/api/manga/{manga_id}/chapters", response_model=list[schemas.ChapterOut], dependencies=[Depends(web_auth)])
def list_chapters(manga_id: str, db: Session = Depends(get_db)) -> list[models.Chapter]:
    return db.query(models.Chapter).filter(models.Chapter.manga_id == manga_id).order_by(models.Chapter.sort_order).all()


@app.delete("/api/chapters/{chapter_id}", dependencies=[Depends(web_auth)])
def delete_chapter(chapter_id: str, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict[str, bool]:
    chapter = db.get(models.Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="chapter not found")
    manga_id = chapter.manga_id
    db.delete(chapter)
    db.flush()
    remaining = db.query(models.Chapter).filter(models.Chapter.manga_id == manga_id).order_by(models.Chapter.sort_order).all()
    for index, item in enumerate(remaining, start=1):
        item.sort_order = index
    db.commit()
    shutil.rmtree(settings.library_dir / manga_id / chapter_id, ignore_errors=True)
    return {"ok": True}


@app.patch("/api/manga/{manga_id}/chapters/order", response_model=list[schemas.ChapterOut], dependencies=[Depends(web_auth)])
def update_chapter_order(
    manga_id: str,
    payload: schemas.ChapterOrderUpdate,
    db: Session = Depends(get_db)
) -> list[models.Chapter]:
    if not db.get(models.Manga, manga_id):
        raise HTTPException(status_code=404, detail="manga not found")
    chapters = db.query(models.Chapter).filter(models.Chapter.manga_id == manga_id).all()
    chapter_by_id = {chapter.id: chapter for chapter in chapters}
    requested_ids = payload.chapter_ids
    if len(requested_ids) != len(set(requested_ids)):
        raise HTTPException(status_code=400, detail="duplicate chapter ids")
    if set(requested_ids) != set(chapter_by_id):
        raise HTTPException(status_code=400, detail="chapter ids must match this manga")
    for index, chapter_id in enumerate(requested_ids, start=1):
        chapter_by_id[chapter_id].sort_order = index
    db.commit()
    return db.query(models.Chapter).filter(models.Chapter.manga_id == manga_id).order_by(models.Chapter.sort_order).all()


@app.post("/api/chapters/{chapter_id}/images", response_model=list[schemas.ImageOut], dependencies=[Depends(web_auth)])
async def upload_images(
    chapter_id: str,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> list[models.MangaImage]:
    chapter = db.get(models.Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="chapter not found")
    existing_count = db.query(models.MangaImage).filter(models.MangaImage.chapter_id == chapter_id).count()
    created: list[models.MangaImage] = []
    for offset, upload in enumerate(files):
        image = models.MangaImage(
            chapter_id=chapter_id,
            original_filename=upload.filename or f"page-{offset}",
            page_index=existing_count + offset + 1,
            source_path="",
            content_type=upload.content_type or "application/octet-stream"
        )
        db.add(image)
        db.flush()
        ext = image_extension(image.original_filename, image.content_type)
        destination = settings.library_dir / chapter.manga_id / chapter_id / "source" / f"{image.id}{ext}"
        await save_upload(upload, destination)
        image.source_path = str(destination)
        image.width, image.height = image_size(destination)
        created.append(image)
    db.commit()
    for image in created:
        db.refresh(image)
    return created


@app.get("/api/chapters/{chapter_id}/read", response_model=schemas.ReadResponse, dependencies=[Depends(web_auth)])
def read_chapter(
    chapter_id: str,
    request: Request,
    lang: str,
    mode: str = "strip",
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> schemas.ReadResponse:
    if mode not in {"strip", "page"}:
        raise HTTPException(status_code=400, detail="mode must be strip or page")
    chapter = db.get(models.Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="chapter not found")
    read_lang = (lang or chapter.manga.default_language or "").strip() or DEFAULT_LANGUAGE
    default_language = (chapter.manga.default_language or "").strip()
    siblings = db.query(models.Chapter).filter(models.Chapter.manga_id == chapter.manga_id).order_by(models.Chapter.sort_order).all()
    index = next((idx for idx, item in enumerate(siblings) if item.id == chapter_id), -1)
    pages: list[schemas.ReadPage] = []
    is_default_language = read_lang == default_language
    reader_logger.info(
        "read_chapter chapter_id=%s manga_id=%s lang=%s default_language=%s mode=%s is_default=%s image_count=%s",
        chapter_id,
        chapter.manga_id,
        read_lang,
        default_language,
        mode,
        is_default_language,
        len(chapter.images)
    )
    for image in chapter.images:
        version = db.query(models.ImageVersion).filter(models.ImageVersion.image_id == image.id, models.ImageVersion.language == read_lang).one_or_none()
        has_version = bool(version and version.status == models.VersionStatus.completed and version.file_path)
        status = "source" if is_default_language else version.status.value if version else "missing"
        missing = False if is_default_language else not has_version
        raw_url = f"/api/files/{image.id}?lang={read_lang}" if has_version and not is_default_language else f"/api/files/{image.id}"
        url = _asset_url(raw_url, request, settings)
        reader_logger.info(
            "read_page image_id=%s page=%s lang=%s status=%s missing=%s url=%s source_path=%s version_path=%s",
            image.id,
            image.page_index,
            read_lang,
            status,
            missing,
            url,
            image.source_path,
            version.file_path if version else ""
        )
        pages.append(schemas.ReadPage(
            image_id=image.id,
            page_index=image.page_index,
            url=url,
            status=status,
            language=read_lang,
            missing=missing
        ))
    return schemas.ReadResponse(
        chapter_id=chapter_id,
        mode=mode,  # type: ignore[arg-type]
        language=read_lang,
        pages=pages,
        previous_chapter_id=siblings[index - 1].id if index > 0 else None,
        next_chapter_id=siblings[index + 1].id if 0 <= index < len(siblings) - 1 else None
    )


@app.get("/api/files/{image_id}", dependencies=[Depends(web_auth)])
def serve_image(image_id: str, lang: str = "", db: Session = Depends(get_db)) -> FileResponse:
    image = db.get(models.MangaImage, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="image not found")
    image_lang = (lang or "").strip()
    path = Path(image.source_path)
    source = "source"
    if image_lang:
        version = db.query(models.ImageVersion).filter(models.ImageVersion.image_id == image_id, models.ImageVersion.language == image_lang).one_or_none()
        if version and version.status == models.VersionStatus.completed and version.file_path:
            path = Path(version.file_path)
            source = "translation"
        else:
            reader_logger.info(
                "serve_image fallback_to_source image_id=%s lang=%s version_status=%s version_path=%s",
                image_id,
                image_lang,
                version.status.value if version else "missing",
                version.file_path if version else ""
            )
    if not path.exists():
        reader_logger.error("serve_image missing_file image_id=%s lang=%s source=%s path=%s", image_id, image_lang, source, path)
        raise HTTPException(status_code=404, detail="file not found")
    reader_logger.info("serve_image image_id=%s lang=%s source=%s path=%s", image_id, image_lang, source, path)
    return FileResponse(path)


@app.post("/api/translate/manga/{manga_id}", response_model=schemas.TranslationTaskOut, dependencies=[Depends(web_auth)])
def translate_manga(
    manga_id: str,
    payload: schemas.TranslateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> models.TranslationTask:
    if not db.get(models.Manga, manga_id):
        raise HTTPException(status_code=404, detail="manga not found")
    task = create_translation_task(db, "manga", manga_id, payload)
    background_tasks.add_task(run_translation_task_sync, task.id, settings, options_from_payload(payload, settings))
    return task


@app.post("/api/translate/chapter/{chapter_id}", response_model=schemas.TranslationTaskOut, dependencies=[Depends(web_auth)])
def translate_chapter(
    chapter_id: str,
    payload: schemas.TranslateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> models.TranslationTask:
    if not db.get(models.Chapter, chapter_id):
        raise HTTPException(status_code=404, detail="chapter not found")
    task = create_translation_task(db, "chapter", chapter_id, payload)
    background_tasks.add_task(run_translation_task_sync, task.id, settings, options_from_payload(payload, settings))
    return task


@app.post("/api/translate/image/{image_id}", response_model=schemas.TranslationTaskOut, dependencies=[Depends(web_auth)])
def translate_image(
    image_id: str,
    payload: schemas.TranslateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings)
) -> models.TranslationTask:
    if not db.get(models.MangaImage, image_id):
        raise HTTPException(status_code=404, detail="image not found")
    task = create_translation_task(db, "image", image_id, payload)
    background_tasks.add_task(run_translation_task_sync, task.id, settings, options_from_payload(payload, settings))
    return task


@app.get("/api/translate/tasks/{task_id}", response_model=schemas.TranslationTaskOut, dependencies=[Depends(web_auth)])
def get_translation_task(task_id: str, db: Session = Depends(get_db)) -> models.TranslationTask:
    task = db.get(models.TranslationTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@app.get("/api/translate/tasks/{task_id}/events", dependencies=[Depends(web_auth)])
def get_translation_task_events(task_id: str, db: Session = Depends(get_db)) -> dict:
    task = db.get(models.TranslationTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    images = _images_for_scope(db, task.scope_type, task.scope_id)
    items = []
    for image in images:
        version = (
            db.query(models.ImageVersion)
            .filter(models.ImageVersion.image_id == image.id, models.ImageVersion.language == task.target_language)
            .one_or_none()
        )
        items.append({
            "image_id": image.id,
            "page_index": image.page_index,
            "filename": image.original_filename,
            "status": version.status.value if version else "missing",
            "message": version.error if version else "",
            "translated": bool(version and version.file_path),
            "translated_url": version.translated_url if version else ""
        })
    return {
        "task_id": task.id,
        "status": task.status.value,
        "completed": task.completed,
        "failed": task.failed,
        "total": task.total,
        "message": task.error,
        "items": items
    }


@app.post("/api/export/manga/{manga_id}", response_model=schemas.ExportTaskOut, dependencies=[Depends(web_auth)])
def export_manga(manga_id: str, payload: schemas.ExportRequest, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> models.ExportTask:
    if not db.get(models.Manga, manga_id):
        raise HTTPException(status_code=404, detail="manga not found")
    return create_export(db, settings, "manga", manga_id, payload)


@app.post("/api/export/chapter/{chapter_id}", response_model=schemas.ExportTaskOut, dependencies=[Depends(web_auth)])
def export_chapter(chapter_id: str, payload: schemas.ExportRequest, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> models.ExportTask:
    if not db.get(models.Chapter, chapter_id):
        raise HTTPException(status_code=404, detail="chapter not found")
    return create_export(db, settings, "chapter", chapter_id, payload)


@app.get("/api/export/tasks/{task_id}", response_model=schemas.ExportTaskOut, dependencies=[Depends(web_auth)])
def get_export_task(task_id: str, db: Session = Depends(get_db)) -> models.ExportTask:
    task = db.get(models.ExportTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@app.get("/api/exports/download/{task_id}", dependencies=[Depends(web_auth)])
def download_export(task_id: str, db: Session = Depends(get_db)) -> FileResponse:
    task = db.get(models.ExportTask, task_id)
    if not task or not task.file_path:
        raise HTTPException(status_code=404, detail="export not found")
    path = Path(task.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="export file not found")
    return FileResponse(path, filename=path.name)


def _frontend_dist() -> Path | None:
    dist = FRONTEND_DIST.resolve()
    index = dist / "index.html"
    if index.is_file():
        return dist
    return None


def _frontend_file(full_path: str) -> Path | None:
    dist = _frontend_dist()
    if not dist:
        return None
    requested = (dist / full_path).resolve()
    if not requested.is_relative_to(dist) or not requested.is_file():
        return None
    return requested


def _frontend_index() -> FileResponse:
    dist = _frontend_dist()
    if not dist:
        raise HTTPException(status_code=404, detail="frontend dist not found")
    return FileResponse(dist / "index.html")


@app.get("/", include_in_schema=False)
def serve_frontend_root() -> FileResponse:
    return _frontend_index()


@app.get("/{full_path:path}", include_in_schema=False)
def serve_frontend(full_path: str) -> FileResponse:
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="not found")
    file_path = _frontend_file(full_path)
    if file_path:
        return FileResponse(file_path)
    return _frontend_index()
