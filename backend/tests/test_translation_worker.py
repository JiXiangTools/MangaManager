import asyncio
import io
import os
import tempfile
from pathlib import Path
from typing import Any

os.environ.setdefault("MANGAMANAGER_TEMP_PASSWORD", "testpass")
_tmp = tempfile.TemporaryDirectory()
os.environ.setdefault("MANGAMANAGER_DATA_DIR", str(Path(_tmp.name) / "data"))
os.environ.setdefault("MANGAMANAGER_DATABASE_URL", f"sqlite:///{Path(_tmp.name) / 'test.db'}")

from PIL import Image  # noqa: E402

from app import models  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.schemas import TranslateRequest  # noqa: E402
from app.storage import ensure_data_dirs  # noqa: E402
from app.translation_client import APP_SOURCE, APP_VERSION, TranslationClient  # noqa: E402
from app.translation import create_translation_task  # noqa: E402
from app.translation_worker import TranslationWorkerOptions, run_translation_task  # noqa: E402


def png_bytes(color: tuple[int, int, int] = (40, 90, 180)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (8, 10), color=color).save(out, format="PNG")
    return out.getvalue()


def make_task(target_language: str = "en", image_count: int = 1) -> tuple[str, list[str]]:
    init_db()
    settings = get_settings()
    ensure_data_dirs(settings)
    db = SessionLocal()
    try:
        manga = models.Manga(name="Worker Book", default_language="zh-CN")
        db.add(manga)
        db.flush()
        chapter = models.Chapter(manga_id=manga.id, title="Chapter", sort_order=1)
        db.add(chapter)
        db.flush()
        image_ids: list[str] = []
        for index in range(image_count):
            source = settings.library_dir / manga.id / chapter.id / "source" / f"page-{index}.png"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(png_bytes((40 + index, 90, 180)))
            image = models.MangaImage(
                chapter_id=chapter.id,
                original_filename=f"page-{index}.png",
                page_index=index + 1,
                source_path=str(source),
                content_type="image/png",
                width=8,
                height=10
            )
            db.add(image)
            db.flush()
            image_ids.append(image.id)
        db.commit()

        task = create_translation_task(
            db,
            "chapter",
            chapter.id,
            TranslateRequest(source_language="zh-CN", target_language=target_language, model_id="CTD", font_id="auto")
        )
        return task.id, image_ids
    finally:
        db.close()


class SuccessfulAsyncProxyClient:
    def __init__(self) -> None:
        self.submitted: list[str] = []
        self.max_active = 0
        self.active = 0

    async def submit_proxy_translate_async(self, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["source_language"] == "zh-CN"
        assert kwargs["target_language"] == "en"
        assert kwargs["model_id"] == "CTD"
        assert kwargs["font_style"] == "auto"
        assert Path(kwargs["file_path"]).exists()
        self.submitted.append(kwargs["image_id"])
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        return {"plugin_id": f"plugin-{kwargs['image_id']}", "status": "queued", "done": False, "translated_url": ""}

    async def wait_proxy_translate_async_result(self, *, plugin_id: str, timeout_seconds: float = 900.0, poll_interval_seconds: float = 1.5) -> dict[str, Any]:
        return {"plugin_id": plugin_id, "status": "completed", "done": True, "translated_url": f"/translated/{plugin_id}.png"}

    async def download_file(self, url: str) -> tuple[bytes, str]:
        return png_bytes((20, 160, 70)), "image/png"


class FailingAsyncProxyClient(SuccessfulAsyncProxyClient):
    async def submit_proxy_translate_async(self, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("async submit failed")


def test_translation_worker_completes_async_proxy_task() -> None:
    task_id, image_ids = make_task(image_count=2)
    settings = get_settings()
    db = SessionLocal()
    client = SuccessfulAsyncProxyClient()
    try:
        task = asyncio.run(
            run_translation_task(
                task_id,
                settings,
                TranslationWorkerOptions(user_id="user-1", email="user@example.test", access_token="token", concurrency=2, poll_interval_seconds=0),
                client=client,
                db=db
            )
        )

        assert task.status == models.TaskStatus.completed
        assert task.completed == 2
        assert task.failed == 0
        assert sorted(client.submitted) == sorted(image_ids)
        assert client.max_active <= 2
        for image_id in image_ids:
            version = db.query(models.ImageVersion).filter_by(image_id=image_id, language="en").one()
            assert version.status == models.VersionStatus.completed
            assert Path(version.file_path).exists()
            assert version.translated_url.startswith("/translated/plugin-")
    finally:
        db.close()


def test_translation_worker_marks_task_failed_when_async_submit_fails() -> None:
    task_id, image_ids = make_task()
    settings = get_settings()
    db = SessionLocal()
    try:
        task = asyncio.run(
            run_translation_task(
                task_id,
                settings,
                TranslationWorkerOptions(user_id="user-1", email="user@example.test", access_token="token", poll_interval_seconds=0),
                client=FailingAsyncProxyClient(),
                db=db
            )
        )
        version = db.query(models.ImageVersion).filter_by(image_id=image_ids[0], language="en").one()

        assert task.status == models.TaskStatus.failed
        assert task.completed == 0
        assert task.failed == 1
        assert version.status == models.VersionStatus.failed
        assert "async submit failed" in version.error
    finally:
        db.close()


def test_async_proxy_submit_uses_manager_source_and_app_version(monkeypatch: Any, tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"plugin_id": "plugin-1", "status": "queued"}

    class FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def post(self, url: str, **kwargs: Any) -> FakeResponse:
            captured["url"] = url
            captured.update(kwargs)
            return FakeResponse()

    monkeypatch.setattr("app.translation_client.httpx.AsyncClient", FakeAsyncClient)
    image_path = tmp_path / "source.png"
    image_path.write_bytes(png_bytes())

    client = TranslationClient(
        "https://www.mangatranslate.com",
        access_token="token-1",
        email="user@example.test",
        user_id="user-1"
    )

    result = asyncio.run(
        client.submit_proxy_translate_async(
            file_path=image_path,
            source_language="zh-CN",
            target_language="en",
            model_id="CTD",
            font_style="auto",
            image_id="image-1"
        )
    )

    assert result["plugin_id"] == "plugin-1"
    assert captured["url"] == "https://plugin-server.mangatranslate.com/api/v1/translated/async"
    assert captured["data"]["from"] == APP_SOURCE == "manager"
    assert captured["data"]["version"] == APP_VERSION == "1.0.0"
