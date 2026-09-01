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

# Importing config loads .env; auth must not depend on api.main's import order.
from src import config as _config  # noqa: F401

router = APIRouter(prefix="/api")

TOKEN_TTL_SECONDS = 7 * 24 * 3600  # 7 days


# Accept both the documented names and the shorter ones people actually put
# in .env. A silent name mismatch here disables auth entirely rather than
# failing loudly, so read every plausible spelling.
_USER_VARS = ("APP_USERNAME", "USER_NAME", "USERNAME", "APP_USER")
_PASS_VARS = ("APP_PASSWORD", "PASSWORD", "APP_PASS")


def _first_env(names: tuple[str, ...]) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def _creds() -> tuple[str, str]:
    return _first_env(_USER_VARS), _first_env(_PASS_VARS)


def auth_enabled() -> bool:
    username, password = _creds()
    return bool(username and password)


def _secret() -> bytes:
    secret = os.getenv("AUTH_SECRET") or _first_env(_PASS_VARS) or "dev-secret"
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
    username = verify_token(token) if token else None
    return {
        "auth_required": auth_enabled(),
        "authenticated": bool(username),
        "username": username,
    }


@router.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    if not auth_enabled():
        raise HTTPException(status_code=404, detail="Auth not configured")
    expected_user, expected_pass = _creds()
    # Compare as bytes: hmac.compare_digest raises TypeError on non-ASCII str,
    # which would surface as a 500 instead of a clean 401. Both comparisons
    # always run so the response time does not reveal which half failed.
    user_ok = hmac.compare_digest(username.encode("utf-8"), expected_user.encode("utf-8"))
    pass_ok = hmac.compare_digest(password.encode("utf-8"), expected_pass.encode("utf-8"))
    if not (user_ok and pass_ok):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"token": create_token(username), "username": username}


@router.post("/logout")
def logout():
    return {"ok": True}
