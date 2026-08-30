from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SESSIONS_DIR = Path(__file__).resolve().parent.parent / "sessions"


def new_session_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]


def save_session(session_id: str, data: dict[str, Any]) -> None:
    SESSIONS_DIR.mkdir(exist_ok=True)
    path = SESSIONS_DIR / f"{session_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def load_session(session_id: str) -> dict[str, Any] | None:
    path = SESSIONS_DIR / f"{session_id}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_sessions() -> list[str]:
    if not SESSIONS_DIR.exists():
        return []
    return sorted([p.stem for p in SESSIONS_DIR.glob("*.json")], reverse=True)
