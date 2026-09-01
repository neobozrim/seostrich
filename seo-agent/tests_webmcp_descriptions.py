"""A visiting agent has nothing but these descriptions.

For a WebMCP integration the tool description IS the interface: an external
agent cannot read the source, so anything it must know to call the tool
correctly — what comes back, when to reach for it, and whether it spends money
or changes state — has to be in the text.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SRC = Path("ui/lib/webmcp.ts").read_text(encoding="utf-8")

ok = fail = 0


def chk(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS {label}")
    else:
        fail += 1
        print(f"  FAIL {label} {extra}")


blocks = re.findall(
    r"name: '(seo_[a-z_]+)',\s*\n\s*title: '([^']*)',\s*\n\s*description:\s*\n?\s*((?:'[^']*'\s*\+?\s*)+)",
    SRC,
)
DESCS = {n: (t, ' '.join(re.findall(r"'([^']*)'", d))) for n, t, d in blocks}

WRITES = {
    "seo_promote_cluster", "seo_discard_cluster", "seo_propose_cluster",
    "seo_rerun_cluster_research", "seo_submit_feedback", "seo_restore_defaults",
}
SPENDS = {"seo_propose_cluster", "seo_rerun_cluster_research"}

print(f"1. every tool is documented ({len(DESCS)} found)")
chk("every registered tool has a parsed description",
    len(DESCS) == SRC.count("      name: 'seo_"),
    f"{len(DESCS)} parsed vs {SRC.count(chr(34) if False else chr(39).join(['      name: ', '']))}")

print("2. descriptions are substantial")
for name, (title, desc) in sorted(DESCS.items()):
    chk(f"{name:<30} {len(desc.split()):>3} words", len(desc.split()) >= 25,
        f"too thin: {desc[:60]}")

print("3. each says when to reach for it")
for name, (_, desc) in sorted(DESCS.items()):
    chk(f"{name:<30} says when", "use " in desc.lower())

print("4. money and mutation are declared")
for name in sorted(SPENDS):
    chk(f"{name:<30} declares its DataForSEO cost",
        "dataforseo call" in DESCS[name][1].lower(), DESCS[name][1][:70])
for name in sorted(DESCS):
    desc = DESCS[name][1].lower()
    if name in WRITES:
        chk(f"{name:<30} declares it writes",
            "writes to the run" in desc or "discards" in desc or "destructive" in desc,
            desc[-70:])
    else:
        chk(f"{name:<30} declares it is read-only", "read-only" in desc, desc[-70:])

print("5. no stale claims after the scoring change")
for name, (_, desc) in DESCS.items():
    chk(f"{name:<30} no invented-score language",
        "combined score" not in desc.lower() and "seo/geo/combined" not in desc.lower(),
        desc[:70])

print("6. titles are distinct and human")
titles = [t for t, _ in DESCS.values()]
chk("all titles unique", len(set(titles)) == len(titles))
chk("no title is just the tool name", not any(t.startswith("seo_") for t in titles))

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
