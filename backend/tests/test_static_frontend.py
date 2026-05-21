import os
import tempfile
from pathlib import Path

os.environ["MANGAMANAGER_TEMP_PASSWORD"] = "testpass"
_tmp = tempfile.TemporaryDirectory()
os.environ["MANGAMANAGER_DATA_DIR"] = str(Path(_tmp.name) / "data")
os.environ["MANGAMANAGER_DATABASE_URL"] = f"sqlite:///{Path(_tmp.name) / 'test.db'}"

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402


def test_static_frontend_serves_index_routes_and_assets(monkeypatch, tmp_path) -> None:
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id=\"root\">MangaManager</div>", encoding="utf-8")
    (assets / "app.js").write_text("window.loaded = true;", encoding="utf-8")
    monkeypatch.setattr(main, "FRONTEND_DIST", dist)

    with TestClient(main.app) as client:
        root = client.get("/")
        assert root.status_code == 200
        assert "MangaManager" in root.text

        nested_route = client.get("/library/books/123")
        assert nested_route.status_code == 200
        assert "MangaManager" in nested_route.text

        asset = client.get("/assets/app.js")
        assert asset.status_code == 200
        assert "window.loaded" in asset.text


def test_static_frontend_does_not_swallow_unknown_api_routes(monkeypatch, tmp_path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><div>frontend</div>", encoding="utf-8")
    monkeypatch.setattr(main, "FRONTEND_DIST", dist)

    with TestClient(main.app) as client:
        response = client.get("/api/does-not-exist")
        assert response.status_code == 404
        assert response.json()["detail"] == "not found"
