import json
from pathlib import Path
from typing import Any

import httpx

from .config import Settings


def _shared_catalog_path() -> Path:
    return Path(__file__).resolve().parents[2] / "shared" / "catalogs.json"


def load_local_catalogs() -> dict[str, Any]:
    return json.loads(_shared_catalog_path().read_text("utf-8"))


def _selectable(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in items if item.get("key") and item.get("enabled", True) is not False and item.get("selectable", True) is not False]


async def fetch_translation_catalogs(settings: Settings) -> dict[str, Any]:
    local = load_local_catalogs()
    models = {"source": "fallback", "defaultModel": "CTD", "items": local["fallbackModels"]}
    fonts = {"source": "fallback", "defaultStyle": "auto", "items": local["fallbackFonts"]}
    async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
        try:
            res = await client.get(f"{settings.translation_base_url.rstrip('/')}/api/v1/api/models", headers={"Accept": "application/json"})
            res.raise_for_status()
            data = res.json()
            items = _selectable(data.get("recognition_models", []))
            if items:
                keys = {item["key"] for item in items}
                default_model = data.get("default_recognition_model") if data.get("default_recognition_model") in keys else "CTD"
                models = {"source": "remote", "defaultModel": default_model, "items": items}
        except Exception:
            pass
        try:
            res = await client.get(f"{settings.translation_base_url.rstrip('/')}/api/v1/api/fonts", headers={"Accept": "application/json"})
            res.raise_for_status()
            data = res.json()
            items = _selectable(data.get("font_styles", []))
            if items:
                keys = {item["key"] for item in items}
                default_style = data.get("default_font_style") if data.get("default_font_style") in keys else "auto"
                fonts = {"source": "remote", "defaultStyle": default_style, "items": items}
        except Exception:
            pass
    return {
        "uiLanguages": local["uiLanguages"],
        "sourceLanguages": local["sourceLanguages"],
        "targetLanguages": local["targetLanguages"],
        "models": models,
        "fonts": fonts,
        "outputFormats": local["outputFormats"]
    }
