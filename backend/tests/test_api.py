import io
import os
import tempfile
import zipfile
from pathlib import Path

os.environ["MANGAMANAGER_TEMP_PASSWORD"] = "testpass"
_tmp = tempfile.TemporaryDirectory()
os.environ["MANGAMANAGER_DATA_DIR"] = str(Path(_tmp.name) / "data")
os.environ["MANGAMANAGER_DATABASE_URL"] = f"sqlite:///{Path(_tmp.name) / 'test.db'}"

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.main import app  # noqa: E402


def image_bytes() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (12, 16), color=(180, 80, 40)).save(out, format="PNG")
    return out.getvalue()


def login(client: TestClient) -> None:
    response = client.post("/api/local/web-auth/login", json={"password": "testpass"})
    assert response.status_code == 200


def test_auth_blocks_business_api() -> None:
    with TestClient(app) as client:
        response = client.get("/api/manga")
        assert response.status_code == 401


def test_desktop_header_bypasses_web_password_gate() -> None:
    with TestClient(app) as client:
        response = client.get("/api/manga", headers={"X-MangaManager-Client": "desktop"})
        assert response.status_code == 200
        assert response.json() == []


def test_manga_chapter_upload_read_translate_and_export() -> None:
    with TestClient(app) as client:
        login(client)

        manga = client.post("/api/manga", json={"name": "Book", "homepage": "https://example.test", "default_language": "zh-CN"}).json()
        chapter = client.post(f"/api/manga/{manga['id']}/chapters", json={"title": "Chapter 1", "number": "1", "sort_order": 1}).json()

        upload = client.post(
            f"/api/chapters/{chapter['id']}/images",
            files=[("files", ("page.png", image_bytes(), "image/png"))]
        )
        assert upload.status_code == 200
        assert upload.json()[0]["width"] == 12

        source_read = client.get(f"/api/chapters/{chapter['id']}/read?lang=zh-CN&mode=strip")
        assert source_read.status_code == 200
        source_body = source_read.json()
        assert source_body["pages"][0]["missing"] is False
        assert source_body["pages"][0]["status"] == "source"
        assert "desktop_token" not in source_body["pages"][0]["url"]

        desktop_source_read = client.get(
            f"/api/chapters/{chapter['id']}/read?lang=zh-CN&mode=strip",
            headers={"X-MangaManager-Client": "desktop"}
        )
        assert desktop_source_read.status_code == 200
        assert desktop_source_read.json()["pages"][0]["missing"] is False

        read = client.get(f"/api/chapters/{chapter['id']}/read?lang=en&mode=strip")
        assert read.status_code == 200
        body = read.json()
        assert body["pages"][0]["missing"] is True
        assert body["pages"][0]["status"] == "missing"

        task = client.post(
            f"/api/translate/chapter/{chapter['id']}",
            json={"source_language": "zh-CN", "target_language": "en", "model_id": "CTD", "font_id": "auto"}
        )
        assert task.status_code == 200
        assert task.json()["total"] == 1

        export = client.post(
            f"/api/export/chapter/{chapter['id']}",
            json={"language": "en", "image_format": "jpg", "skip_missing": False}
        )
        assert export.status_code == 200
        export_body = export.json()
        assert export_body["status"] == "completed"
        assert Path(export_body["file_path"]).exists()


def test_catalogs_include_reference_languages_and_fallbacks() -> None:
    with TestClient(app) as client:
        login(client)
        response = client.get("/api/translate/catalogs")
        assert response.status_code == 200
        body = response.json()
        assert "zh-CN" in body["sourceLanguages"]
        assert "hi-en" in body["targetLanguages"]
        assert body["models"]["items"]
        assert body["fonts"]["items"]


def test_translation_login_endpoint_uses_reference_contract(monkeypatch) -> None:
    async def fake_login(self, email: str, password: str) -> dict[str, str]:
        assert email == "user@example.test"
        assert password == "secret"
        return {"user_id": "u1", "access_token": "token"}

    monkeypatch.setattr("app.translation_client.TranslationClient.login_email", fake_login)
    with TestClient(app) as client:
        login(client)
        response = client.post(
            "/api/translate/auth/login",
            json={"email": "user@example.test", "password": "secret", "base_url": "https://example.test"}
        )
        assert response.status_code == 200
        assert response.json() == {"user_id": "u1", "access_token": "token", "email": "", "raw_cookie": ""}


def test_translation_cookie_login_endpoint_uses_reference_contract(monkeypatch) -> None:
    async def fake_login(self, raw_cookie: str) -> dict[str, str]:
        assert raw_cookie == "access_token=token; user_id=u1"
        return {"user_id": "u1", "access_token": "token", "email": "user@example.test", "raw_cookie": raw_cookie}

    monkeypatch.setattr("app.translation_client.TranslationClient.login_cookie", fake_login)
    with TestClient(app) as client:
        login(client)
        response = client.post(
            "/api/translate/auth/cookie",
            json={"raw_cookie": "access_token=token; user_id=u1", "base_url": "https://example.test"}
        )
        assert response.status_code == 200
        assert response.json() == {
            "user_id": "u1",
            "access_token": "token",
            "email": "user@example.test",
            "raw_cookie": "access_token=token; user_id=u1"
        }


def test_manga_cover_upload_and_fetch() -> None:
    with TestClient(app) as client:
        login(client)
        manga = client.post(
            "/api/manga/upload",
            data={"name": "Cover Book", "homepage": "", "default_language": "zh-CN"},
            files=[("cover_image", ("cover.png", image_bytes(), "image/png"))]
        ).json()
        assert manga["cover_image_id"]
        cover = client.get(f"/api/manga/{manga['id']}/cover")
        assert cover.status_code == 200
        assert cover.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_desktop_folder_import_counts_only_visible_images(tmp_path: Path) -> None:
    root = tmp_path / "Folder Book"
    chapter = root / "Chapter 1"
    hidden = root / ".hidden"
    chapter.mkdir(parents=True)
    hidden.mkdir()
    (chapter / "notes.txt").write_text("not image", "utf-8")
    (hidden / "hidden.png").write_bytes(image_bytes())
    (chapter / ".hidden-page.png").write_bytes(image_bytes())
    (chapter / "page-001.png").write_bytes(image_bytes())

    with TestClient(app) as client:
        response = client.post(
            "/api/desktop/import-folder",
            headers={"X-MangaManager-Client": "desktop"},
            json={"folder_path": str(root), "default_language": "en", "max_images": 1}
        )
        assert response.status_code == 200
        manga = response.json()
        assert manga["name"] == "Folder Book"
        assert manga["default_language"] == "en"
        chapters = client.get(f"/api/manga/{manga['id']}/chapters", headers={"X-MangaManager-Client": "desktop"}).json()
        assert len(chapters) == 1
        read = client.get(f"/api/chapters/{chapters[0]['id']}/read?lang=en&mode=strip", headers={"X-MangaManager-Client": "desktop"}).json()
        assert len(read["pages"]) == 1


def test_desktop_folder_import_enforces_image_limit(tmp_path: Path) -> None:
    root = tmp_path / "Large Book"
    chapter = root / "Chapter 1"
    chapter.mkdir(parents=True)
    (chapter / "page-001.png").write_bytes(image_bytes())
    (chapter / "page-002.png").write_bytes(image_bytes())

    with TestClient(app) as client:
        response = client.post(
            "/api/desktop/import-folder",
            headers={"X-MangaManager-Client": "desktop"},
            json={"folder_path": str(root), "default_language": "en", "max_images": 1}
        )
        assert response.status_code == 400
        assert "maximum is 1" in response.text


def test_chapter_order_can_be_rearranged() -> None:
    with TestClient(app) as client:
        login(client)
        manga = client.post("/api/manga", json={"name": "Ordered Book", "homepage": "", "default_language": "zh-CN"}).json()
        first = client.post(f"/api/manga/{manga['id']}/chapters", json={"title": "First", "number": "1", "sort_order": 1}).json()
        second = client.post(f"/api/manga/{manga['id']}/chapters", json={"title": "Second", "number": "2", "sort_order": 2}).json()
        third = client.post(f"/api/manga/{manga['id']}/chapters", json={"title": "Third", "number": "3", "sort_order": 3}).json()

        response = client.patch(
            f"/api/manga/{manga['id']}/chapters/order",
            json={"chapter_ids": [third["id"], first["id"], second["id"]]}
        )

        assert response.status_code == 200
        assert [chapter["title"] for chapter in response.json()] == ["Third", "First", "Second"]
        chapters = client.get(f"/api/manga/{manga['id']}/chapters").json()
        assert [chapter["sort_order"] for chapter in chapters] == [1, 2, 3]
        assert [chapter["id"] for chapter in chapters] == [third["id"], first["id"], second["id"]]


def test_delete_manga_and_chapter_remove_records_and_files() -> None:
    with TestClient(app) as client:
        login(client)
        manga = client.post("/api/manga", json={"name": "Delete Book", "homepage": "", "default_language": "zh-CN"}).json()
        first = client.post(f"/api/manga/{manga['id']}/chapters", json={"title": "First", "number": "1", "sort_order": 1}).json()
        second = client.post(f"/api/manga/{manga['id']}/chapters", json={"title": "Second", "number": "2", "sort_order": 2}).json()
        for chapter in (first, second):
            response = client.post(
                f"/api/chapters/{chapter['id']}/images",
                files=[("files", ("page.png", image_bytes(), "image/png"))]
            )
            assert response.status_code == 200

        chapter_dir = Path(os.environ["MANGAMANAGER_DATA_DIR"]) / "library" / manga["id"] / first["id"]
        assert chapter_dir.exists()
        delete_chapter = client.delete(f"/api/chapters/{first['id']}")
        assert delete_chapter.status_code == 200
        assert not chapter_dir.exists()
        chapters = client.get(f"/api/manga/{manga['id']}/chapters").json()
        assert [chapter["id"] for chapter in chapters] == [second["id"]]
        assert chapters[0]["sort_order"] == 1

        manga_dir = Path(os.environ["MANGAMANAGER_DATA_DIR"]) / "library" / manga["id"]
        assert manga_dir.exists()
        delete_manga = client.delete(f"/api/manga/{manga['id']}")
        assert delete_manga.status_code == 200
        assert not manga_dir.exists()
        assert client.get(f"/api/manga/{manga['id']}").status_code == 404


def test_manga_export_zip_contains_all_chapters_as_requested_format() -> None:
    with TestClient(app) as client:
        login(client)
        manga = client.post("/api/manga", json={"name": "Export Book", "homepage": "", "default_language": "zh-CN"}).json()
        chapter_one = client.post(f"/api/manga/{manga['id']}/chapters", json={"title": "One", "number": "1", "sort_order": 1}).json()
        chapter_two = client.post(f"/api/manga/{manga['id']}/chapters", json={"title": "Two", "number": "2", "sort_order": 2}).json()
        for chapter in (chapter_one, chapter_two):
            response = client.post(
                f"/api/chapters/{chapter['id']}/images",
                files=[("files", ("page.png", image_bytes(), "image/png"))]
            )
            assert response.status_code == 200

        export = client.post(
            f"/api/export/manga/{manga['id']}",
            json={"language": "en", "image_format": "png", "skip_missing": False}
        )
        assert export.status_code == 200
        export_body = export.json()
        assert export_body["status"] == "completed"
        with zipfile.ZipFile(export_body["file_path"]) as archive:
            names = archive.namelist()
        assert len(names) == 2
        assert all(name.endswith(".png") for name in names)

        download = client.get(f"/api/exports/download/{export_body['id']}")
        assert download.status_code == 200
        assert download.content[:2] == b"PK"
