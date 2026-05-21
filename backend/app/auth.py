import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException, Request, Response

from .config import Settings


SESSION_COOKIE = "mm_session"


def hash_password(password: str, salt: str | None = None) -> str:
    raw_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), raw_salt.encode("utf-8"), 120_000)
    return f"pbkdf2_sha256${raw_salt}${digest.hex()}"


def verify_password(password: str, settings: Settings) -> bool:
    if settings.temp_password_hash:
        try:
            algo, salt, expected = settings.temp_password_hash.split("$", 2)
        except ValueError:
            return False
        if algo != "pbkdf2_sha256":
            return False
        actual = hash_password(password, salt).split("$", 2)[2]
        return hmac.compare_digest(actual, expected)
    if settings.temp_password:
        return hmac.compare_digest(password, settings.temp_password)
    return False


def create_session(response: Response, app_state: object) -> str:
    token = secrets.token_urlsafe(32)
    sessions = getattr(app_state, "sessions", None)
    if sessions is None:
        sessions = {}
        setattr(app_state, "sessions", sessions)
    sessions[token] = datetime.utcnow() + timedelta(hours=12)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=12 * 60 * 60)
    return token


def require_session(request: Request) -> None:
    token = request.cookies.get(SESSION_COOKIE, "")
    sessions = getattr(request.app.state, "sessions", {})
    expires = sessions.get(token)
    if not expires or expires < datetime.utcnow():
        raise HTTPException(status_code=401, detail="web auth required")

