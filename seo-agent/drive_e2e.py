"""Drive a real chat run against the local backend and print the event stream.

Usage: python drive_e2e.py "<message>" [session_id]
Prints every SSE event with a timestamp so stalls are visible, then a summary
of stages reached, tools called, and DataForSEO spend.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

# Windows consoles default to cp1252, which cannot encode the emoji agents
# routinely emit — printing the answer crashed the driver after a 388s run.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.getenv("API_BASE", "http://127.0.0.1:8001")
ENV = Path(__file__).resolve().parent.parent / ".env"


def _env(name: str) -> str:
    if not ENV.exists():
        return ""
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    return ""


def login() -> dict:
    user, password = _env("USER_NAME"), _env("PASSWORD")
    check = requests.get(f"{BASE}/api/auth/check", timeout=10).json()
    if not check.get("auth_required"):
        return {}
    r = requests.post(f"{BASE}/api/login", data={"username": user, "password": password}, timeout=15)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def run(message: str, session_id: str | None = None) -> None:
    headers = login()
    data = {"message": message}
    if session_id:
        data["session_id"] = session_id

    t0 = time.time()
    sid = session_id
    stages, tools, texts, errors = [], [], [], []
    last = t0

    with requests.post(f"{BASE}/api/chat/stream", data=data, headers=headers,
                       stream=True, timeout=(15, 900)) as resp:
        resp.raise_for_status()
        for raw in resp.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data: "):
                continue
            ev = json.loads(raw[6:])
            now = time.time()
            gap, last = now - last, now
            kind = ev.get("type")

            if kind == "session_id":
                sid = ev["session_id"]
                print(f"[{now-t0:6.1f}s] session {sid}")
            elif kind == "text":
                texts.append(ev.get("content", ""))
            elif kind == "status":
                print(f"[{now-t0:6.1f}s] status   {ev.get('content','')[:110]}")
            elif kind == "activity":
                detail = ev.get("detail") or ev.get("tool") or ev.get("event") or ""
                print(f"[{now-t0:6.1f}s] +{gap:5.1f}s  activity {ev.get('event','')}: {str(detail)[:100]}")
            elif kind == "stage":
                stages.append(ev.get("stage_id"))
                print(f"[{now-t0:6.1f}s] STAGE    {ev.get('stage_id')} ({ev.get('label','')})")
            elif kind == "tool_start":
                tools.append(ev.get("tool"))
                print(f"[{now-t0:6.1f}s] tool>    {ev.get('tool')} {json.dumps(ev.get('args',{}),ensure_ascii=False)[:140]}")
            elif kind == "tool_end":
                print(f"[{now-t0:6.1f}s] tool<    {ev.get('tool')} success={ev.get('success')}")
            elif kind == "error":
                errors.append(ev.get("content", ""))
                print(f"[{now-t0:6.1f}s] ERROR    {ev.get('content','')[:400]}")
            elif kind == "done":
                print(f"[{now-t0:6.1f}s] done")

    answer = "".join(texts)
    print("\n" + "=" * 78)
    print(f"session   : {sid}")
    print(f"wall      : {time.time()-t0:.1f}s")
    print(f"stages    : {stages or '(none)'}")
    print(f"tools     : {tools or '(none)'}")
    print(f"errors    : {errors or '(none)'}")
    print("=" * 78)
    print("ANSWER:\n" + (answer or "(empty)"))

    if sid:
        try:
            r = requests.get(f"{BASE}/api/runs/chat-{sid}", headers=headers, timeout=15)
            if r.ok:
                run_doc = r.json()
                print("\nRUN DOC:")
                print(f"  status: {run_doc.get('status')}  error: {run_doc.get('error')}")
                for s in run_doc.get("stages", []):
                    art = s.get("artifact") or {}
                    size = len(json.dumps(art, ensure_ascii=False, default=str))
                    print(f"  stage {s['id']:<14} {s.get('status'):<6} artifact {size:>7} chars  "
                          f"keys={list(art)[:6]}")
        except Exception as exc:
            print(f"  (run doc unavailable: {exc})")


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
