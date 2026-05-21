from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

import httpx

from .constants import DEFAULT_LANGUAGE

APP_SOURCE = "manager"


def load_app_version() -> str:
    for parent in Path(__file__).resolve().parents:
        product_path = parent / "shared" / "product.json"
        if product_path.exists():
            try:
                return str(json.loads(product_path.read_text(encoding="utf-8")).get("version") or "1.0.0")
            except Exception:
                return "1.0.0"
    return "1.0.0"


APP_VERSION = load_app_version()


def guess_mime(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    if ext == ".png":
        return "image/png"
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if ext == ".webp":
        return "image/webp"
    if ext == ".gif":
        return "image/gif"
    if ext == ".bmp":
        return "image/bmp"
    if ext in {".tif", ".tiff"}:
        return "image/tiff"
    if ext == ".avif":
        return "image/avif"
    return "application/octet-stream"


def resolve_boolean_like(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    normalized = str(value or "").strip().lower()
    return normalized in {"true", "1", "yes", "done"}


def resolve_async_task_status(data: Any) -> dict[str, Any]:
    raw = data if isinstance(data, dict) else {}
    nested = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    status = str(raw.get("status") or nested.get("status") or "").strip().lower()
    plugin_id = str(raw.get("plugin_id") or raw.get("pluginId") or nested.get("plugin_id") or nested.get("pluginId") or "").strip()
    mt_id = str(raw.get("mt_id") or raw.get("mtId") or nested.get("mt_id") or nested.get("mtId") or "").strip()
    translated_url = str(
        raw.get("translated_url")
        or raw.get("translatedUrl")
        or nested.get("translated_url")
        or nested.get("translatedUrl")
        or ""
    ).strip()
    done_value = raw.get("done", nested.get("done"))
    done = (
        resolve_boolean_like(done_value)
        or bool(translated_url)
        or status in {"completed", "complete", "success", "succeeded", "finished", "failed", "error", "cancelled", "canceled"}
    )
    return {
        "plugin_id": plugin_id,
        "mt_id": mt_id,
        "status": status,
        "done": done,
        "translated_url": translated_url,
        "raw": raw
    }


def is_async_task_failed(status: str) -> bool:
    return str(status or "").strip().lower() in {"failed", "error"}


def resolve_proxy_base(base_url: str, explicit: str = "") -> str:
    if explicit.strip():
        return explicit.strip().rstrip("/")
    fallback = "https://plugin-server.mangatranslate.com"
    parsed = urlparse(str(base_url or "").strip())
    host = parsed.hostname or ""
    if host == "plugin-server.mangatranslate.com" or host.startswith("plugin-server."):
        return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    if host in {"mangatranslate.com", "www.mangatranslate.com"}:
        return fallback
    return fallback


class TranslationClient:
    def __init__(
        self,
        base_url: str,
        access_token: str = "",
        proxy_base: str = "",
        email: str = "",
        user_id: str = "",
        raw_cookie: str = ""
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.proxy_base = resolve_proxy_base(base_url, proxy_base)
        self.access_token = access_token
        self.email = email
        self.user_id = user_id
        self.raw_cookie = raw_cookie

    @staticmethod
    def _cookie_value(raw_cookie: str, name: str) -> str:
        target = name.lower().strip()
        for part in (raw_cookie or "").split(";"):
            item = part.strip()
            if not item or "=" not in item:
                continue
            key, value = item.split("=", 1)
            if key.strip().lower() != target:
                continue
            return value.strip().strip('"').strip("'")
        return ""

    @classmethod
    def _csrf_headers(cls, raw_cookie: str) -> dict[str, str]:
        token = cls._cookie_value(raw_cookie, "csrftoken") or cls._cookie_value(raw_cookie, "csrf_token")
        return {"X-CSRF-Token": token} if token else {}

    @staticmethod
    def _resolve_user_id(data: Any, fallback: str = "") -> str:
        raw = data if isinstance(data, dict) else {}
        nested = raw.get("user") if isinstance(raw.get("user"), dict) else {}
        payload = raw.get("data") if isinstance(raw.get("data"), dict) else {}
        payload_user = payload.get("user") if isinstance(payload.get("user"), dict) else {}
        candidates = [
            raw.get("user_id"),
            raw.get("userId"),
            nested.get("id"),
            nested.get("user_id"),
            payload.get("user_id"),
            payload.get("userId"),
            payload_user.get("id"),
            payload_user.get("user_id"),
            fallback
        ]
        for candidate in candidates:
            value = str(candidate or "").strip()
            if value:
                return value
        return ""

    @staticmethod
    def _resolve_email(data: Any, fallback: str = "") -> str:
        raw = data if isinstance(data, dict) else {}
        nested = raw.get("user") if isinstance(raw.get("user"), dict) else {}
        profile = raw.get("profile") if isinstance(raw.get("profile"), dict) else {}
        payload = raw.get("data") if isinstance(raw.get("data"), dict) else {}
        payload_user = payload.get("user") if isinstance(payload.get("user"), dict) else {}
        candidates = [
            raw.get("email"),
            raw.get("user_email"),
            nested.get("email"),
            profile.get("email"),
            payload.get("email"),
            payload_user.get("email"),
            fallback
        ]
        for candidate in candidates:
            value = str(candidate or "").strip()
            if value and "@" in value:
                return value
        return ""

    def _auth_headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"Accept": "application/json", **(extra or {})}
        if self.raw_cookie:
            headers["Cookie"] = self.raw_cookie
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        return self._auth_headers(extra)

    async def login_email(self, email: str, password: str) -> dict[str, str]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/auth/login/email",
                json={"email": email, "password": password},
                headers=self._headers({"Content-Type": "application/json"})
            )
            response.raise_for_status()
            data = response.json()
        user_id = self._resolve_user_id(data)
        access_token = str(data.get("access_token") or "").strip()
        resolved_email = self._resolve_email(data, email)
        if not user_id:
            raise ValueError("login response missing user id")
        self.user_id = user_id
        self.email = resolved_email
        self.access_token = access_token
        return {"user_id": user_id, "access_token": access_token, "email": resolved_email}

    async def login_cookie(self, raw_cookie: str) -> dict[str, str]:
        cookie = str(raw_cookie or "").strip()
        if not cookie:
            raise ValueError("raw_cookie is empty")

        headers = {"Content-Type": "application/json", **self._auth_headers(), **self._csrf_headers(cookie)}
        headers["Cookie"] = cookie
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/auth/check-session",
                json={},
                headers=headers
            )
            response.raise_for_status()
            session = response.json()

            dashboard = {}
            try:
                dashboard_res = await client.get(
                    f"{self.base_url}/api/v1/dashboard/user-dashboard?include_subscriptions=1",
                    headers={"Accept": "application/json", **self._auth_headers(), "Cookie": cookie}
                )
                if dashboard_res.ok:
                    dashboard = dashboard_res.json()
            except Exception:
                dashboard = {}

        token = self._cookie_value(cookie, "access_token") or self._cookie_value(cookie, "access-token")
        user_id = self._resolve_user_id(session, self._resolve_user_id(dashboard, token))
        email = self._resolve_email(session, self._resolve_email(dashboard))
        if not user_id and token:
            user_id = token
        if not user_id:
            raise ValueError("cookie login response missing user id")

        self.raw_cookie = cookie
        self.user_id = user_id
        self.email = email
        self.access_token = token
        return {"user_id": user_id, "access_token": token, "email": email, "raw_cookie": cookie}

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
        user_id = self.user_id.strip()
        if not user_id:
            raise ValueError("translation user_id is required")

        buf = file_path.read_bytes()
        md5 = hashlib.md5(buf).hexdigest()
        mime = guess_mime(file_path)
        upload_name_raw = original_asset_id or image_id or file_path.stem or "image"
        upload_name = "".join(ch if ch.isalnum() or ch in "_.-" else "_" for ch in upload_name_raw)[:120] or "image"
        ext = file_path.suffix.lstrip(".") or "webp"

        data = {
            "image_url": md5,
            "page_url": str(page_url or ""),
            "source_language": source_language or "en",
            "target_language": target_language or DEFAULT_LANGUAGE,
            "model_id": model_id or "CTD",
            "font_style": font_style or "auto",
            "access_token": self.access_token,
            "email": self.email,
            "version": APP_VERSION,
            "from": APP_SOURCE,
            "user_id": user_id,
            "image_id": image_id or md5,
            "original_asset_id": original_asset_id or image_id or md5
        }
        files = {"image": (f"{upload_name}.{ext}", buf, mime)}
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.proxy_base}/api/v1/translated/async",
                data=data,
                files=files,
                headers=self._headers()
            )
            response.raise_for_status()
            parsed = resolve_async_task_status(response.json())
        if not parsed["plugin_id"]:
            raise ValueError(f"proxy async submit success but plugin_id missing: body={parsed['raw']}")
        return parsed

    async def get_proxy_translate_async_task(self, plugin_id: str) -> dict[str, Any]:
        query = {"access_token": self.access_token}
        if self.email:
            query["email"] = self.email
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{self.proxy_base}/api/v1/translated/async/{plugin_id}?{urlencode(query)}",
                headers=self._headers()
            )
            response.raise_for_status()
            return resolve_async_task_status(response.json())

    async def wait_proxy_translate_async_result(
        self,
        *,
        plugin_id: str,
        timeout_seconds: float = 900.0,
        poll_interval_seconds: float = 1.5
    ) -> dict[str, Any]:
        import asyncio
        import time

        started_at = time.monotonic()
        while time.monotonic() - started_at < max(1.0, timeout_seconds):
            status = await self.get_proxy_translate_async_task(plugin_id)
            if is_async_task_failed(status["status"]):
                raise RuntimeError(f"proxy async task failed: plugin_id={plugin_id} status={status['status']}")
            if status["done"] and status["translated_url"]:
                return status
            await asyncio.sleep(poll_interval_seconds)
        raise TimeoutError("proxy async poll timeout")

    async def download_file(self, url: str) -> tuple[bytes, str]:
        download_url = url if url.startswith(("http://", "https://")) else urljoin(f"{self.proxy_base}/", url.lstrip("/"))
        async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as client:
            response = await client.get(download_url, headers=self._headers({"Accept": "*/*"}))
            response.raise_for_status()
            return response.content, response.headers.get("content-type", "")
