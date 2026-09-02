"""The WebMCP-facing endpoints, against a real run fixture.

These back the tools a visiting agent calls, so they are tested at the HTTP
layer rather than by calling the functions directly.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # seo-agent/
# Auth off for the test client; the real credential path is covered by tests_auth.
for v in ("APP_USERNAME", "APP_PASSWORD", "USER_NAME", "PASSWORD"):
    os.environ.pop(v, None)

from fastapi.testclient import TestClient

from src import runs
import api.main as main_mod
from api import auth

auth._creds = lambda: ("", "")  # noqa: E731 - disable auth for these calls

client = TestClient(main_mod.app)
ok = fail = 0


def chk(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS {label}")
    else:
        fail += 1
        print(f"  FAIL {label} {extra}")


RID = "test-webmcp-run"
runs.save_run(RID, {
    "id": RID, "project": "Test", "title": "webmcp fixture", "status": "done",
    "stages": [
        {"id": "intake", "label": "Intake", "status": "done",
         "artifact": {"market": "US-EN", "locale": {"location_code": 2840, "language_code": "en"}}},
        {"id": "keywords", "label": "Keyword discovery", "status": "done",
         "artifact": {"count": 3, "keywords": [
             {"keyword": "ai product manager", "volume": 3600, "difficulty": 9, "cpc": 11.88, "intent": "informational"},
             {"keyword": "agentic commerce", "volume": 20, "difficulty": 3, "cpc": 0.0, "intent": "commercial"},
             {"keyword": "orphan term", "volume": 5, "difficulty": 1, "cpc": 0.5, "intent": "informational"},
         ]}},
        {"id": "clusters", "label": "Clusters", "status": "done",
         "artifact": {
             "selected": True,
             "clusters": [{"cluster_name": "AI PM Role", "head_term": "ai product manager",
                           "keywords": [{"keyword": "ai product manager"}]}],
             "discarded": [{"cluster_name": "Commerce", "head_term": "agentic commerce",
                            "reason": "off-topic", "keywords": [{"keyword": "agentic commerce"}]}],
         }},
    ],
})

print("1. flow catalog (seo_list_flows)")
r = client.get("/api/flows")
chk("200", r.status_code == 200, str(r.status_code))
body = r.json()
chk("lists both flows", {f["id"] for f in body["flows"]} == {"keyword_strategy", "geo_demand"})
chk("market is a required input everywhere",
    all(any(i["name"] == "market" for i in f["required_inputs"]) for f in body["flows"]))
chk("planned flows are declared, not hidden", len(body["planned"]) >= 1)
chk("markets offered", len(body["markets"]) > 5)

print("2. flat keyword table (seo_get_keywords)")
r = client.get(f"/api/runs/{RID}/keywords")
chk("200", r.status_code == 200, str(r.status_code))
kw = r.json()
chk("all keywords returned", kw["count"] == 3, str(kw["count"]))
chk("market carried", kw["market"] == "US-EN")
first = kw["keywords"][0]
chk("carries volume/difficulty/cpc/intent",
    all(first.get(f) is not None for f in ("volume", "difficulty", "cpc", "intent")), str(first))
chk("maps keyword -> cluster", first["cluster"] == "AI PM Role", str(first))
chk("discarded cluster membership shown too",
    any(k["cluster"] == "Commerce" for k in kw["keywords"]))
chk("unclustered keyword has cluster=None",
    any(k["cluster"] is None for k in kw["keywords"]))

print("3. filtering by cluster")
r = client.get(f"/api/runs/{RID}/keywords", params={"cluster": "AI PM Role"})
chk("filtered", r.json()["count"] == 1, str(r.json()["count"]))
r = client.get(f"/api/runs/{RID}/keywords", params={"cluster": "ai pm role"})
chk("case-insensitive", r.json()["count"] == 1)
r = client.get(f"/api/runs/{RID}/keywords", params={"cluster": "nope"})
chk("unknown cluster -> empty, not error", r.status_code == 200 and r.json()["count"] == 0)

print("4. error paths")
chk("unknown run -> 404", client.get("/api/runs/does-not-exist/keywords").status_code == 404)
chk("rerun unknown run -> 404",
    client.post("/api/runs/does-not-exist/clusters/rerun",
                json={"cluster_name": "x"}).status_code == 404)
r = client.post(f"/api/runs/{RID}/clusters/rerun", json={"cluster_name": "no such cluster"})
chk("rerun unknown cluster -> ok:false with reason",
    r.status_code == 200 and r.json().get("ok") is False and "not found" in r.json().get("error", ""),
    str(r.json())[:120])
chk("rerun requires a name",
    client.post(f"/api/runs/{RID}/clusters/rerun", json={}).status_code == 422)

print("5. health handshake (stale-backend guard)")
h = client.get("/api/health").json()
chk("reports a version", bool(h.get("version")))
chk("version matches the UI constant",
    h["version"] in Path("ui/lib/api.ts").read_text(encoding="utf-8"), h.get("version"))
chk("lists the flows it can run", set(h.get("flows", [])) == {"keyword_strategy", "geo_demand"})

runs.delete_run(RID) if hasattr(runs, "delete_run") else None
print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
