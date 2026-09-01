"""FastAPI backend for SEO Agent UI."""
import os
import sys

# Force UTF-8 encoding for Windows
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import json
import asyncio
import sys
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import Depends, FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse, PlainTextResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
import tempfile
import os

# Add parent directory to Python path so we can import src
sys.path.insert(0, str(Path(__file__).parent.parent))

# GSC service-account creds may arrive as raw JSON (hosted environments)
_gsc_json = os.getenv("GSC_CREDENTIALS_JSON")
if _gsc_json:
    _gsc_path = os.getenv("GSC_CREDENTIALS_PATH", "/tmp/gsc-console-creds.json")
    Path(_gsc_path).parent.mkdir(parents=True, exist_ok=True)
    Path(_gsc_path).write_text(_gsc_json, encoding="utf-8")
    os.environ["GSC_CREDENTIALS_PATH"] = _gsc_path

from src.orchestrator import run_orchestrator
from src import memory, runs
from api.auth import router as auth_router, require_auth

app = FastAPI(title="SEO Agent API")
app.include_router(auth_router)


@app.on_event("startup")
def _seed_default_runs():
    """Populate the example run(s) on first boot so judges see real data."""
    runs.seed_defaults(force=False)
    # Runs left in "running" are orphans from a crash or restart — close them
    # so the Run view never shows forever-running pipelines.
    for summary in runs.list_runs():
        if summary.get("status") == "running":
            run = runs.get_run(summary["id"])
            if run:
                run["status"] = "error"
                run["error"] = "interrupted by server restart"
                run["ended"] = datetime.now(timezone.utc).isoformat()
                runs.save_run(summary["id"], run)

# CORS middleware — origins come from CORS_ORIGINS (comma-separated)
_cors_origins = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Bumped whenever the API contract the UI depends on changes. The UI warns
# when it does not recognise the value. This exists because a stale backend
# left running on another port (:8000, shipped-code from hours earlier, auth
# disabled, no /api/flows) silently served the UI for a whole session: every
# browser test validated the wrong process, and the missing endpoints looked
# like frontend bugs.
API_VERSION = "2026-09-01.governance"


@app.get("/api/health")
async def health():
    """Health check endpoint. `version` lets the UI detect a stale backend."""
    from src import flows
    from src.config import memory_enabled

    return {
        "status": "ok",
        "version": API_VERSION,
        "flows": list(flows.REGISTRY),
        # The System panel only shows memory and improvement proposals. With
        # memory switched off it is an empty room, so the UI hides its entry
        # point rather than offering a dead end.
        "memory_enabled": memory_enabled(),
        "port": int(os.getenv("PORT", "8001")),
    }


def _memory_lines(text: str) -> List[str]:
    """Split memory file content into entries, dropping blank lines."""
    return [line for line in text.split("\n") if line.strip()]


@app.get("/api/flows")
async def get_flows(_auth: None = Depends(require_auth)):
    """The flow catalog: what the agent can do, and what each flow needs first.

    Drives the homepage cards, the deterministic plan preview and the WebMCP
    flow tools, so all three stay in sync with src/flows.py.
    """
    from src import flows
    from src import market

    return {
        "flows": flows.list_flows(),
        "planned": [{"id": k, "label": v} for k, v in flows.PLANNED.items()],
        "markets": market.catalog(),
    }


@app.get("/api/memory")
async def get_memory(_auth: None = Depends(require_auth)):
    """Get current memory state."""
    return {
        "facts": _memory_lines(memory.read_facts()),
        "learnings": _memory_lines(memory.read_learnings()),
        "decisions": _memory_lines(memory.read_decisions()),
        "tasks": _memory_lines(memory.read_tasks()),
    }


@app.get("/api/sessions")
async def get_sessions(_auth: None = Depends(require_auth)):
    """Get list of sessions."""
    from src import session as session_store
    sessions = session_store.list_sessions()
    return [{"id": sid, "createdAt": sid.split("-")[0]} for sid in sessions[:20]]


@app.get("/api/artifacts")
async def get_artifacts(_auth: None = Depends(require_auth)):
    """List artifacts produced by agent runs."""
    artifacts_dir = memory._get_memory_dir() / "artefacts"
    if not artifacts_dir.exists():
        return []
    items = []
    for path in sorted(artifacts_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if path.is_file():
            items.append({
                "name": path.name,
                "size": path.stat().st_size,
                "modified": path.stat().st_mtime,
            })
    return items


@app.get("/api/artifacts/{name}")
async def get_artifact_content(name: str, _auth: None = Depends(require_auth)):
    """Return the content of a single artifact (path-traversal safe)."""
    if "/" in name or "\\" in name or name.startswith(".."):
        raise HTTPException(status_code=404, detail="Not found")
    path = memory._get_memory_dir() / "artefacts" / name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return PlainTextResponse(path.read_text(encoding="utf-8", errors="replace"))


class FeedbackIn(BaseModel):
    text: str
    author: str = "judge"


@app.get("/api/runs")
async def list_runs(_auth: None = Depends(require_auth)):
    """List stored pipeline runs (summaries)."""
    return runs.list_runs()


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str, _auth: None = Depends(require_auth)):
    """Return one full run with all its stage artifacts."""
    run = runs.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.post("/api/runs/{run_id}/feedback")
async def add_run_feedback(
    run_id: str, body: FeedbackIn, _auth: None = Depends(require_auth)
):
    """Attach a feedback note to a run (used by the Run view + WebMCP)."""
    run = runs.add_feedback(run_id, body.text, body.author)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"ok": True, "feedback": run["feedback"]}


class PinIn(BaseModel):
    pinned: bool = True
    note: str = ""


@app.post("/api/runs/{run_id}/pin")
async def pin_run(run_id: str, body: PinIn, _auth: None = Depends(require_auth)):
    """Pin a run so it leads the home canvas regardless of recency."""
    result = runs.set_pinned(run_id, body.pinned, body.note)
    if result is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return result


@app.post("/api/runs/restore-defaults")
async def restore_default_runs(_auth: None = Depends(require_auth)):
    """Reset example runs back to the shipped seed data."""
    restored = runs.restore_defaults()
    return {"restored": restored}


class ClusterNameIn(BaseModel):
    cluster_name: str


class ClusterDiscardIn(BaseModel):
    cluster_name: str
    reason: str = ""


class ClusterProposeIn(BaseModel):
    topic: str


@app.get("/api/runs/{run_id}/clusters")
async def get_run_clusters(run_id: str, _auth: None = Depends(require_auth)):
    """Selected AND discarded clusters with stats and discard reasons (Run view + WebMCP)."""
    from src import cluster_governance

    data = cluster_governance.list_clusters_all(run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return data


@app.get("/api/runs/{run_id}/keywords")
async def get_run_keywords(
    run_id: str, cluster: str = "", _auth: None = Depends(require_auth)
):
    """Flat keyword table with volume, difficulty, intent and CPC.

    Exposed so an external agent can do its own analysis (filter by
    difficulty, sort by CPC, spot intent mismatches) instead of re-deriving
    the numbers. All four metrics already arrive in the DataForSEO responses
    the pipeline makes, so this costs nothing extra.
    """
    run = runs.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    stages = {s["id"]: s for s in run.get("stages", [])}
    rows = list((stages.get("keywords", {}).get("artifact", {}) or {}).get("keywords", []))

    # Which cluster each keyword ended up in (selected or discarded).
    member_of: dict[str, str] = {}
    art = (stages.get("clusters", {}).get("artifact", {}) or {})
    for pool in ("clusters", "discarded"):
        for entry in art.get(pool) or []:
            name = entry.get("cluster_name") or entry.get("name") or ""
            for kw in entry.get("keywords") or []:
                key = kw.get("keyword") if isinstance(kw, dict) else kw
                if key:
                    member_of.setdefault(str(key).lower(), name)

    out = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("keyword"):
            continue
        name = str(row["keyword"])
        entry = {
            "keyword": name,
            "volume": row.get("volume"),
            "difficulty": row.get("difficulty"),
            "cpc": row.get("cpc"),
            "intent": row.get("intent"),
            "cluster": member_of.get(name.lower()),
        }
        if cluster and (entry["cluster"] or "").lower() != cluster.lower():
            continue
        out.append(entry)

    return {
        "run_id": run_id,
        "market": (stages.get("intake", {}).get("artifact", {}) or {}).get("market"),
        "count": len(out),
        "keywords": out,
    }


class ClusterRerunIn(BaseModel):
    cluster_name: str


@app.post("/api/runs/{run_id}/clusters/rerun")
async def rerun_run_cluster(
    run_id: str, body: ClusterRerunIn, _auth: None = Depends(require_auth)
):
    """Re-run keyword research for ONE cluster (1 DataForSEO call), in place."""
    from src import cluster_governance

    result = await asyncio.to_thread(
        cluster_governance.rerun_cluster_research, run_id, body.cluster_name
    )
    if not result.get("ok") and result.get("error") == "run not found":
        raise HTTPException(status_code=404, detail="Run not found")
    return result


class CitationCheckIn(BaseModel):
    domain: str
    location_code: int = 2840
    language_code: str = "en"


@app.post("/api/ai-citations")
async def ai_citation_check(body: CitationCheckIn, _auth: None = Depends(require_auth)):
    """Which AI answers cite a domain, and who is quoted alongside it.

    Not tied to a run: it answers "is this site cited yet" for any domain, so
    an external agent can check the user's own site or size up a competitor.
    """
    from src.tools.dataforseo import ai_mentions_domain

    return await asyncio.to_thread(
        ai_mentions_domain, body.domain,
        location_code=body.location_code, language_code=body.language_code,
    )


@app.get("/api/runs/{run_id}/governance")
async def get_run_governance(run_id: str, _auth: None = Depends(require_auth)):
    """How this strategy was shaped: every promote/discard/propose, and by whom."""
    from src import cluster_governance

    result = cluster_governance.governance_history(run_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail="Run not found")
    return result


@app.get("/api/runs/{run_id}/activity")
async def get_run_activity(run_id: str, cursor: int = 0, _auth: None = Depends(require_auth)):
    """Live activity feed (LLM rounds, graph nodes, tool starts/ends) for a run."""
    if runs.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    from src import pipeline_recorder

    events, next_cursor = pipeline_recorder.new_activity(run_id, cursor)
    return {"events": events, "cursor": next_cursor}


@app.get("/api/runs/{run_id}/stages/{stage_id}")
async def get_run_stage(run_id: str, stage_id: str, _auth: None = Depends(require_auth)):
    """One stage artifact of a run (inspectable by the UI and external agents)."""
    run = runs.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    stage = next((s for s in run.get("stages", []) if s["id"] == stage_id), None)
    if stage is None:
        raise HTTPException(status_code=404, detail="Stage not found")
    return stage


@app.post("/api/runs/{run_id}/clusters/promote")
async def promote_run_cluster(run_id: str, body: ClusterNameIn, _auth: None = Depends(require_auth)):
    """Promote a discarded cluster back into the selection."""
    from src import cluster_governance

    result = cluster_governance.promote_cluster(run_id, body.cluster_name, by="webmcp")
    if not result.get("ok") and result.get("error") == "run not found":
        raise HTTPException(status_code=404, detail="Run not found")
    return result


@app.post("/api/runs/{run_id}/clusters/discard")
async def discard_run_cluster(run_id: str, body: ClusterDiscardIn, _auth: None = Depends(require_auth)):
    """Discard a selected cluster (kept in the discarded set with its stats)."""
    from src import cluster_governance

    result = cluster_governance.discard_cluster(run_id, body.cluster_name, body.reason, by="webmcp")
    if not result.get("ok") and result.get("error") == "run not found":
        raise HTTPException(status_code=404, detail="Run not found")
    return result


@app.post("/api/runs/{run_id}/clusters/propose")
async def propose_run_cluster(run_id: str, body: ClusterProposeIn, _auth: None = Depends(require_auth)):
    """Propose a new cluster via a scoped keyword re-seed on one topic (1 DataForSEO call)."""
    from src import cluster_governance

    result = await asyncio.to_thread(cluster_governance.propose_cluster, run_id, body.topic, None, None, "webmcp")
    if not result.get("ok") and result.get("error") == "run not found":
        raise HTTPException(status_code=404, detail="Run not found")
    return result


@app.get("/api/memory/file/{filename}")
async def get_memory_file(filename: str, _auth: None = Depends(require_auth)):
    """Get content of a specific memory file."""
    # Validate filename to prevent directory traversal
    allowed_files = [
        "facts.md", "learnings.md", "decisions.md", "tasks.md",
        "runs-summaries.md", "artefacts-index.md", "memory-archive.md"
    ]
    
    if filename not in allowed_files:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Get memory directory path from memory module
    memory_dir = memory._get_memory_dir()
    file_path = memory_dir / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    content = file_path.read_text(encoding="utf-8")
    return PlainTextResponse(content)


@app.get("/api/memory/improvements")
async def get_improvements(_auth: None = Depends(require_auth)):
    """Get list of improvement proposals."""
    improvements_dir = memory._get_memory_dir() / "improvements"
    
    if not improvements_dir.exists():
        return []
    
    improvements = []
    for file_path in sorted(improvements_dir.glob("proposal-*.md"), reverse=True):
        try:
            content = file_path.read_text(encoding="utf-8")
            
            # Parse improvement metadata from markdown
            lines = content.split("\n")
            topic = ""
            category = ""
            rationale = ""
            status = "pending"
            
            for line in lines:
                if line.startswith("# "):
                    topic = line[2:].strip()
                elif "**Category:**" in line:
                    category = line.split("**Category:**")[1].strip()
                elif "**Status:**" in line:
                    status = line.split("**Status:**")[1].strip()
                elif "## Rationale" in line:
                    # Get the next non-empty line after Rationale header
                    idx = lines.index(line) + 1
                    while idx < len(lines) and not lines[idx].strip():
                        idx += 1
                    if idx < len(lines):
                        rationale = lines[idx].strip()
            
            improvements.append({
                "id": file_path.stem,
                "topic": topic,
                "category": category,
                "rationale": rationale,
                "status": status,
                "timestamp": file_path.stat().st_mtime,
            })
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
            continue
    
    return improvements


class StopIn(BaseModel):
    session_id: str


@app.post("/api/chat/stop")
async def chat_stop(body: StopIn, _auth: None = Depends(require_auth)):
    """Ask a running chat stream to stop (cooperative: takes effect between steps)."""
    from src.orchestrator import request_stop

    return {"ok": request_stop(body.session_id)}


@app.post("/api/chat/stream")
async def chat_stream(
    request: Request,
    message: str = Form(...),
    session_id: Optional[str] = Form(None),
    files: List[UploadFile] = File(default=[]),
    _auth: None = Depends(require_auth),
):
    """Stream chat responses from orchestrator."""

    # Save uploaded files temporarily
    attachments = []
    for file in files:
        if file.filename:
            content = await file.read()
            attachments.append({
                "name": file.filename,
                "content": content.decode("utf-8", errors="ignore"),
                "type": file.content_type,
            })

    async def generate():
        """Generate streaming response with real-time status updates."""
        try:
            # Prepare context with attachments
            full_message = message
            if attachments:
                attachment_context = "\n\nAttached files:\n"
                for att in attachments:
                    attachment_context += f"\n{att['name']}:\n{att['content'][:500]}...\n"
                full_message += attachment_context

            from src.orchestrator import run_orchestrator_stream, request_stop

            # Run the sync generator in a thread and stream results
            gen = run_orchestrator_stream(full_message, session_id)
            chat_sid: Optional[str] = session_id

            # Pull from the generator and poll for client disconnect
            # CONCURRENTLY. Checking only after a chunk arrived meant a client
            # that left during a long LLM call was never noticed: the abandoned
            # run kept burning LLM and DataForSEO calls to completion. Observed
            # 2026-09-01 - a killed client left a run sitting on round 1 for
            # four minutes until it was stopped by hand.
            DISCONNECT_POLL_SECONDS = 1.0
            pending = None
            disconnected = False

            while True:
                if pending is None:
                    pending = asyncio.create_task(asyncio.to_thread(next, gen, None))

                done, _ = await asyncio.wait({pending}, timeout=DISCONNECT_POLL_SECONDS)

                if pending not in done:
                    # Generator still working - this is exactly the window in
                    # which a disconnect used to go unseen.
                    if not disconnected and chat_sid and await request.is_disconnected():
                        disconnected = True
                        request_stop(chat_sid)
                    continue

                try:
                    chunk = pending.result()
                except StopIteration:
                    break
                finally:
                    pending = None

                if chunk is None:
                    break
                if chunk.get("type") == "session_id":
                    chat_sid = chunk.get("session_id")

                if disconnected:
                    # Client is gone; keep draining so the orchestrator's
                    # finally-block closes the run, but stop writing.
                    continue

                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                # Small delay after text chunks to force separate SSE frames
                if chunk.get("type") == "text":
                    await asyncio.sleep(0.02)
                if chat_sid and await request.is_disconnected():
                    disconnected = True
                    request_stop(chat_sid)

            # Get updated memory state
            memory_state = {
                "facts": _memory_lines(memory.read_facts())[:10],
                "learnings": _memory_lines(memory.read_learnings())[:10],
                "decisions": _memory_lines(memory.read_decisions())[:10],
                "tasks": _memory_lines(memory.read_tasks())[:10],
            }
            memory_chunk = {"type": "memory_update", "memory": memory_state}
            yield f"data: {json.dumps(memory_chunk, ensure_ascii=False)}\n\n"

        except Exception as e:
            import traceback
            traceback.print_exc()
            error_chunk = {"type": "error", "content": str(e)}
            yield f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream; charset=utf-8",
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8001")))
