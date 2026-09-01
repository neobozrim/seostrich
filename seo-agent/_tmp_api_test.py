"""Integration test: governance + stage REST endpoints through the FastAPI layer."""
import io
import os
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_tmp = tempfile.mkdtemp(prefix="seo-api-test-")
os.environ["MEMORY_DIR"] = _tmp
os.environ["SESSIONS_DIR"] = _tmp
os.environ["CACHE_DIR"] = _tmp
# Keep auth disabled (APP_USERNAME/APP_PASSWORD unset)

sys.path.insert(0, os.path.abspath("."))

from unittest.mock import patch  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from src import pipeline_recorder  # noqa: E402
from src.tools import dataforseo  # noqa: E402

RUN = "chat-api-test"
pipeline_recorder.begin_run(RUN, "api test")
pipeline_recorder.record_tool("extract_seeds", {}, {"seeds": ["ai seo tools"]}, True)
pipeline_recorder.record_tool(
    "cluster_keywords",
    {"keywords": [
        {"keyword": "ai seo tools", "volume": 1000, "difficulty": 30, "intent": "commercial"},
        {"keyword": "seo pricing", "volume": 90, "difficulty": 10, "intent": "transactional"},
    ]},
    {"clusters": [
        {"cluster_id": 1, "cluster_name": "AI SEO tooling", "head_term": "ai seo tools", "keywords": ["ai seo tools"]},
        {"cluster_id": 2, "cluster_name": "API pricing", "head_term": "seo pricing", "keywords": ["seo pricing"]},
    ]},
    True,
)
pipeline_recorder.record_tool("select_clusters", {}, {
    "selection": {
        "selected": ["AI SEO tooling"],
        "discarded": [{"cluster_name": "API pricing", "reason": "low volume"}],
    }
}, True)
pipeline_recorder.end_run(RUN)

from api.main import app  # noqa: E402

client = TestClient(app)

# --- GET clusters (selected + discarded) ---
r = client.get(f"/api/runs/{RUN}/clusters")
assert r.status_code == 200, r.text
body = r.json()
assert len(body["selected"]) == 1 and len(body["discarded"]) == 1, body
# The discard reason moved under , where every kind of reason now
# lives under one stable key rather than five differently-named fields.
assert body["discarded"][0]["reasoning"]["decision_reason"] == "low volume"
assert body["discarded"][0]["reasoning"]["decision"] == "discarded"

# --- GET stage artifact ---
r = client.get(f"/api/runs/{RUN}/stages/clusters")
assert r.status_code == 200 and r.json()["id"] == "clusters", r.text
r = client.get(f"/api/runs/{RUN}/stages/bogus")
assert r.status_code == 404, r.text

# --- POST promote ---
r = client.post(f"/api/runs/{RUN}/clusters/promote", json={"cluster_name": "API pricing"})
assert r.status_code == 200 and r.json()["ok"] is True, r.text

# --- POST discard (back again) ---
r = client.post(f"/api/runs/{RUN}/clusters/discard", json={"cluster_name": "API pricing", "reason": "re-discard"})
assert r.status_code == 200 and r.json()["ok"] is True, r.text

# --- POST propose (mocked DataForSEO) ---
FAKE = [{"keyword": "seo audit tool", "volume": 400, "difficulty": 22, "cpc": 2.0, "intent": "commercial"}]
with patch.object(dataforseo, "keyword_suggestions", lambda *a, **k: FAKE):
    r = client.post(f"/api/runs/{RUN}/clusters/propose", json={"topic": "seo audit tool"})
assert r.status_code == 200, r.text
assert r.json()["ok"] is True and r.json()["proposed"]["name"] == "seo audit tool", r.text

# --- 404s for a missing run ---
assert client.get("/api/runs/nope/clusters").status_code == 404
assert client.post("/api/runs/nope/clusters/promote", json={"cluster_name": "x"}).status_code == 404

# --- validation: propose without topic -> 422 ---
assert client.post(f"/api/runs/{RUN}/clusters/propose", json={}).status_code == 422

print("\nPASS: governance + stage REST endpoints (FastAPI layer)")
