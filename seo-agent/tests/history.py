"""How a strategy was shaped must be recoverable, not just where it ended up.

Every governance op mutates the cluster artifact in place, so without a log
there is no record of what a human changed or why — and for a tool whose point
is collaboration, the shaping IS the story. Asked for the clusters round by
round earlier today, the honest answer was that only the final state existed.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # seo-agent/

from src import cluster_governance as gov
from src import runs as runs_store

ok = fail = 0


def chk(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS {label}")
    else:
        fail += 1
        print(f"  FAIL {label} {extra}")


RID = "test-history-run"
NAMES = ["Alpha", "Beta", "Gamma"]


def fixture():
    runs_store.save_run(RID, {
        "id": RID, "project": "t", "title": "history", "status": "done",
        "stages": [{"id": "clusters", "label": "Clusters", "status": "done", "artifact": {
            "selected": True,
            "clusters": [{"name": n, "cluster_name": n, "keywords": [f"{n}-kw"]} for n in NAMES],
            "discarded": [],
        }}],
    })


print("1. an untouched run has an empty history, not a missing one")
fixture()
h = gov.governance_history(RID)
chk("readable", h["ok"] is True)
chk("empty", h["count"] == 0, str(h["count"]))
chk("says what empty means", "never adjusted" in h["note"])

print("2. every op is recorded, in order, with who and why")
gov.discard_cluster(RID, "Beta", "off-topic for this business", by="webmcp")
gov.promote_cluster(RID, "Beta", by="user")
h = gov.governance_history(RID)
chk("both changes logged", h["count"] == 2, str(h["count"]))
chk("in order", [c["op"] for c in h["changes"]] == ["discard", "promote"],
    str([c["op"] for c in h["changes"]]))
chk("attribution kept", [c["by"] for c in h["changes"]] == ["webmcp", "user"],
    str([c["by"] for c in h["changes"]]))
chk("the discard reason is kept",
    "off-topic" in h["changes"][0]["reason"], h["changes"][0].get("reason", ""))
chk("the promote records what it overrode",
    "off-topic" in str(h["changes"][1].get("was_discarded_for", "")),
    str(h["changes"][1].get("was_discarded_for")))
chk("every entry is timestamped", all(c.get("at") for c in h["changes"]))
chk("target named", all(c.get("cluster") for c in h["changes"]))

print("3. counts make a lost update visible")
chk("discard dropped the count", h["changes"][0]["selected_after"] == 2,
    str(h["changes"][0]["selected_after"]))
chk("promote restored it", h["changes"][1]["selected_after"] == 3,
    str(h["changes"][1]["selected_after"]))
chk("discarded side tracked too",
    [c["discarded_after"] for c in h["changes"]] == [1, 0],
    str([c["discarded_after"] for c in h["changes"]]))

print("4. it is append-only — history is never rewritten")
before = list(h["changes"])
gov.discard_cluster(RID, "Gamma", "thin", by="agent")
after = gov.governance_history(RID)["changes"]
chk("earlier entries untouched", after[:2] == before, "history was rewritten")
chk("the new one is appended", after[-1]["cluster"] == "Gamma" and len(after) == 3)

print("5. the default attribution is the agent")
fixture()
gov.discard_cluster(RID, "Alpha", "weak")
chk("unattributed changes are the agent's",
    gov.governance_history(RID)["changes"][0]["by"] == "agent")

print("6. a missing run says so")
chk("unknown run", gov.governance_history("nope")["ok"] is False)

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
