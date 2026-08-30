"""Shared-account auth: stateless signed bearer tokens.

Auth is active only when APP_USERNAME and APP_PASSWORD are both set,
so local development stays open by default.
"""
import base64
import hashlib
import hmac
import os
import time

from fastapi import APIRouter, Form, HTTPException, Request

router = APIRouter(prefix="/api")

TOKEN_TTL_SECONDS = 7 * 24 * 3600  # 7 days


def _creds() -> tuple[str, str]:
    return os.getenv("APP_USERNAME", ""), os.getenv("APP_PASSWORD", "")


def auth_enabled() -> bool:
    username, password = _creds()
    return bool(username and password)


def _secret() -> bytes:
    secret = os.getenv("AUTH_SECRET") or os.getenv("APP_PASSWORD") or "dev-secret"
    return secret.encode("utf-8")


def create_token(username: str) -> str:
    expires = int(time.time()) + TOKEN_TTL_SECONDS
    payload = f"{username}:{expires}"
    sig = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    raw = f"{payload}:{sig}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def verify_token(token: str) -> str | None:
    """Return the username if the token is valid and unexpired, else None."""
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        username, expires_str, sig = raw.rsplit(":", 2)
        payload = f"{username}:{expires_str}"
        expected = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        if int(expires_str) < int(time.time()):
            return None
        return username
    except Exception:
        return None


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:].strip()
    return None


def require_auth(request: Request) -> None:
    """FastAPI dependency: raises 401 when auth is configured and token is missing/invalid."""
    if not auth_enabled():
        return
    token = _bearer_token(request)
    if not token or verify_token(token) is None:
        raise HTTPException(status_code=401, detail="Not authenticated")


@router.get("/auth/check")
def auth_check(request: Request):
    token = _bearer_token(request)
    return {
        "auth_required": auth_enabled(),
        "authenticated": bool(token and verify_token(token)),
    }


@router.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    if not auth_enabled():
        raise HTTPException(status_code=404, detail="Auth not configured")
    expected_user, expected_pass = _creds()
    user_ok = hmac.compare_digest(username, expected_user)
    pass_ok = hmac.compare_digest(password, expected_pass)
    if not (user_ok and pass_ok):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"token": create_token(username)}


@router.post("/logout")
def logout():
    return {"ok": True}
