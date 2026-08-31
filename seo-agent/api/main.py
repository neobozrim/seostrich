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
from typing import List, Optional
from fastapi import Depends, FastAPI, UploadFile, File, Form, HTTPException
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


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


def _memory_lines(text: str) -> List[str]:
    """Split memory file content into entries, dropping blank lines."""
    return [line for line in text.split("\n") if line.strip()]


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


@app.post("/api/runs/restore-defaults")
async def restore_default_runs(_auth: None = Depends(require_auth)):
    """Reset example runs back to the shipped seed data."""
    restored = runs.restore_defaults()
    return {"restored": restored}


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


@app.post("/api/chat/stream")
async def chat_stream(
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

            from src.orchestrator import run_orchestrator_stream

            # Run the sync generator in a thread and stream results
            gen = run_orchestrator_stream(full_message, session_id)

            while True:
                try:
                    chunk = await asyncio.to_thread(next, gen, None)
                    if chunk is None:
                        break
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                    # Small delay after text chunks to force separate SSE frames
                    if chunk.get("type") == "text":
                        await asyncio.sleep(0.02)
                except StopIteration:
                    break

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
