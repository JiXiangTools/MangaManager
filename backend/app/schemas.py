from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .constants import DEFAULT_LANGUAGE


class MangaCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    homepage: str = ""
    default_language: str = DEFAULT_LANGUAGE
    category: str = ""
    tags: str = ""


class MangaUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    homepage: str | None = None
    default_language: str | None = None
    category: str | None = None
    tags: str | None = None


class FolderImportRequest(BaseModel):
    folder_path: str
    default_language: str = DEFAULT_LANGUAGE
    max_images: int = 5000


class MangaOut(BaseModel):
    id: str
    name: str
    homepage: str
    default_language: str
    cover_image_id: str
    category: str
    tags: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChapterCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    number: str = ""
    sort_order: int = 0


class ChapterUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    number: str | None = None
    sort_order: int | None = None


class ChapterOrderUpdate(BaseModel):
    chapter_ids: list[str] = Field(min_length=1)


class ChapterOut(BaseModel):
    id: str
    manga_id: str
    title: str
    number: str
    sort_order: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ImageOut(BaseModel):
    id: str
    chapter_id: str
    original_filename: str
    page_index: int
    source_path: str
    content_type: str
    width: int
    height: int

    model_config = {"from_attributes": True}


class ReadPage(BaseModel):
    image_id: str
    page_index: int
    url: str
    status: str
    language: str
    missing: bool


class ReadResponse(BaseModel):
    chapter_id: str
    mode: Literal["strip", "page"]
    language: str
    pages: list[ReadPage]
    previous_chapter_id: str | None = None
    next_chapter_id: str | None = None


class TranslateRequest(BaseModel):
    source_language: str
    target_language: str
    model_id: str = "CTD"
    font_id: str = "auto"
    user_id: str = ""
    email: str = ""
    access_token: str = ""
    raw_cookie: str = ""
    base_url: str = ""
    proxy_base: str = ""
    concurrency: int = 3


class TranslationTaskOut(BaseModel):
    id: str
    scope_type: str
    scope_id: str
    source_language: str
    target_language: str
    model_id: str
    font_id: str
    status: str
    total: int
    completed: int
    failed: int
    error: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ExportRequest(BaseModel):
    language: str
    image_format: Literal["webp", "jpg", "png"] = "webp"
    skip_missing: bool = True


class ExportTaskOut(BaseModel):
    id: str
    scope_type: str
    scope_id: str
    language: str
    image_format: str
    status: str
    file_path: str
    error: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PasswordLogin(BaseModel):
    password: str


class TranslationLoginRequest(BaseModel):
    email: str
    password: str
    base_url: str = ""


class TranslationLoginResponse(BaseModel):
    user_id: str
    access_token: str = ""
    email: str = ""
    raw_cookie: str = ""


class TranslationCookieLoginRequest(BaseModel):
    raw_cookie: str
    base_url: str = ""
