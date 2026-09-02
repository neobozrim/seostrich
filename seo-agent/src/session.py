from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_env_sessions_dir = os.getenv("SESSIONS_DIR")
SESSIONS_DIR = (
    Path(_env_sessions_dir)
    if _env_sessions_dir
    else Path(__file__).resolve().parent.parent / "sessions"
)


# A session id becomes a file name, exactly like a run id; validated the
# same way before it touches the filesystem.
_SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def valid_session_id(session_id: str) -> bool:
    return bool(session_id) and bool(_SESSION_ID.match(session_id)) and ".." not in session_id


def session_summary(session_id: str) -> dict[str, Any] | None:
    """What the history list shows: id, when, and the first thing asked."""
    data = load_session(session_id)
    if data is None:
        return None
    first = next(
        (m.get("content") for m in data.get("messages") or []
         if m.get("role") == "user" and isinstance(m.get("content"), str) and m.get("content").strip()),
        "",
    )
    return {
        "id": session_id,
        "createdAt": session_id.split("-")[0],
        "title": " ".join(first.split())[:90],
        "messages": sum(1 for m in data.get("messages") or [] if m.get("role") in ("user", "assistant")),
    }


def new_session_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]


def save_session(session_id: str, data: dict[str, Any]) -> None:
    if not valid_session_id(session_id):
        raise ValueError(f"invalid session id: {session_id!r}")
    SESSIONS_DIR.mkdir(exist_ok=True)
    path = SESSIONS_DIR / f"{session_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def load_session(session_id: str) -> dict[str, Any] | None:
    if not valid_session_id(session_id):
        return None
    path = SESSIONS_DIR / f"{session_id}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_sessions() -> list[str]:
    if not SESSIONS_DIR.exists():
        return []
    return sorted([p.stem for p in SESSIONS_DIR.glob("*.json")], reverse=True)
