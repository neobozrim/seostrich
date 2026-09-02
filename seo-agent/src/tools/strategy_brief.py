"""The brief: the one page a reader acts on.

The graph produces stages — seeds, a universe, clusters, pillars — and the
agent used to write a freeform closing message that lived in the chat and
was never seen again. This is the closing report as a DEFINED stage with a
fixed shape, built from the artefact's own measured data:

  the_call     which pillar first, and why, citing the numbers
  out_answer   who owns the keywords in that space, named
  pieces       six pieces: working title, the exact question each answers,
               the cluster it serves, the keyword it targets
  parked       what was set aside and why

It is regenerated whenever the selection changes — a discard over WebMCP
should change the plan, or the edit meant nothing.

The inputs are assembled deterministically here; only the WORDING is the
model's. Every number the brief can cite is in the input it is given, and the
output is validated against the shape before it is recorded.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone

from .. import llm, runs
from ..config import settings

PIECES = 6

SYSTEM_PROMPT = """You are an SEO strategist writing the one-page brief a content team acts on.
You are given the business, the SELECTED clusters with measured metrics, the content
pillars, the clusters that were PARKED with their reasons, and which competitors own
which keywords. Write the brief. Cite only numbers that appear in the input.

Output JSON only, exactly this shape:
{
  "the_call": {
    "pillar": "the pillar to build first (its exact title)",
    "why": "2-3 sentences: why this one first, with the measured numbers, and why not the biggest one if that is the case"
  },
  "out_answer": [
    {"who": "domain", "for_what": "what they own here, in one clause"}
  ],
  "pieces": [
    {
      "title": "a working title a writer could start from",
      "question": "the exact question this piece answers, as a person would type it",
      "cluster": "the cluster it serves (exact name)",
      "target_keyword": "the one keyword it targets (from the input)",
      "format": "guide | comparison | how-to | list | explainer"
    }
  ],
  "parked": [
    {"cluster": "exact name", "why": "one sentence, from the stated reason"}
  ]
}

Rules:
- Exactly 6 pieces, spread across the selected clusters in proportion to their volume;
  every piece's target_keyword must be a keyword from the input.
- The question is the heading a reader searches for; the first two sentences under it
  must be able to answer it, so make it concrete.
- out_answer names domains from the input only. If none own anything here, say so with
  an empty list.
- parked lists EVERY parked cluster, with the reason given.
- No preamble, no markdown, JSON only."""


def _stage(run: dict, sid: str) -> dict:
    return next((s.get("artifact") or {} for s in run.get("stages", []) if s.get("id") == sid), {})


def build_input(run: dict, business_description: str = "") -> dict:
    """Everything the brief may cite, assembled from the artefact. Deterministic."""
    clusters = _stage(run, "clusters")
    pillars = _stage(run, "pillars").get("pillars") or []
    comp = _stage(run, "competitors")
    intake = _stage(run, "intake")

    selected = []
    for c in clusters.get("clusters") or []:
        m = c.get("metrics") or {}
        stats = c.get("keyword_stats") or {}
        kws = []
        for k in c.get("keywords") or []:
            name = k if isinstance(k, str) else (k or {}).get("keyword", "")
            st = stats.get(name) or {}
            kws.append({"keyword": name, "volume": st.get("volume"), "difficulty": st.get("difficulty"),
                        "owned_by": st.get("owned_by") or []})
        kws.sort(key=lambda x: -(x.get("volume") or 0))
        selected.append({
            "cluster": c.get("cluster_name") or c.get("name"),
            "head_term": c.get("head_term"),
            "total_volume": m.get("total_volume", c.get("total_volume")),
            "max_volume": m.get("max_volume"),
            "avg_difficulty": m.get("avg_difficulty", c.get("avg_difficulty")),
            "why_selected": c.get("selection_reason") or "",
            "keywords": kws[:12],
        })

    parked = [{
        "cluster": d.get("cluster_name") or d.get("name"),
        "total_volume": (d.get("metrics") or {}).get("total_volume", d.get("total_volume")),
        "why": d.get("discard_reason") or "",
    } for d in clusters.get("discarded") or []]

    owners: dict[str, list[str]] = {}
    for c in selected:
        for k in c["keywords"]:
            for d in k.get("owned_by") or []:
                owners.setdefault(d, [])
                if len(owners[d]) < 6:
                    owners[d].append(k["keyword"])

    return {
        "business": (business_description or run.get("title") or "")[:1200],
        "market": intake.get("market") or run.get("project") or "",
        "selected_clusters": selected,
        "pillars": [{"title": p.get("pillar_title"), "type": p.get("pillar_type"),
                     "cluster": p.get("cluster_name"), "priority": p.get("priority"),
                     "rationale": p.get("rationale")} for p in pillars],
        "parked": parked,
        "competitors_own": [{"who": d, "keywords": ks} for d, ks in owners.items()],
        "pieces_wanted": PIECES,
    }


def _valid(brief: dict, inp: dict) -> tuple[bool, str]:
    if not isinstance(brief, dict):
        return False, "not an object"
    call = brief.get("the_call") or {}
    if not (isinstance(call, dict) and call.get("pillar") and call.get("why")):
        return False, "the_call incomplete"
    pieces = brief.get("pieces")
    if not isinstance(pieces, list) or len(pieces) < 1:
        return False, "no pieces"
    known = {k["keyword"].lower() for c in inp["selected_clusters"] for k in c["keywords"] if k.get("keyword")}
    for p in pieces:
        if not (isinstance(p, dict) and p.get("title") and p.get("question")):
            return False, "a piece lacks title or question"
        tk = str(p.get("target_keyword") or "").lower()
        if known and tk and tk not in known:
            return False, f"target_keyword not in input: {tk}"
    if not isinstance(brief.get("parked"), list):
        return False, "parked missing"
    if not isinstance(brief.get("out_answer"), list):
        return False, "out_answer missing"
    return True, ""


def write_brief(run_id: str, business_description: str = "") -> dict:
    """Build the brief for a run and record it as the `brief` stage."""
    run = runs.get_run(run_id)
    if not run:
        return {"ok": False, "error": "run not found"}
    inp = build_input(run, business_description)
    if not inp["selected_clusters"]:
        return {"ok": False, "error": "no selected clusters to brief"}

    user_msg = f"Write the brief.\n\n{llm.format_json(inp)}"
    last_err = ""
    brief = None
    for attempt in range(2):
        try:
            resp = llm.chat(user_msg if attempt == 0 else user_msg + f"\n\nYour previous answer was rejected: {last_err}. Fix it.",
                            system=SYSTEM_PROMPT, model=settings.qwen_model_fast, temperature=0.2, max_tokens=2500)
            cand = llm.parse_json_response(resp)
            ok, why = _valid(cand, inp)
            if ok:
                brief = cand
                break
            last_err = why
        except Exception as e:
            last_err = str(e)[:160]
    if brief is None:
        return {"ok": False, "error": f"brief not produced: {last_err}"}

    pieces = brief["pieces"][:PIECES]
    artifact = {
        "the_call": brief["the_call"],
        "out_answer": brief.get("out_answer") or [],
        "pieces": pieces,
        "parked": brief.get("parked") or [],
        "written_at": datetime.now(timezone.utc).isoformat(),
        "stale": False,
        "based_on": {
            "selected": [c["cluster"] for c in inp["selected_clusters"]],
            "parked": [p["cluster"] for p in inp["parked"]],
        },
    }
    run = runs.get_run(run_id) or run
    stages = run.setdefault("stages", [])
    stage = next((s for s in stages if s.get("id") == "brief"), None)
    if stage is None:
        stage = {"id": "brief", "label": "The brief", "status": "done", "artifact": {}}
        stages.append(stage)
    stage["artifact"] = artifact
    stage["status"] = "done"
    runs.save_run(run_id, run)
    return {"ok": True, "brief": artifact}


def mark_stale(run: dict, reason: str = "") -> None:
    """The selection changed under the brief. Say so on the artefact; the
    refresh follows in the background."""
    for s in run.get("stages", []):
        if s.get("id") == "brief":
            s.setdefault("artifact", {})["stale"] = True
            s["artifact"]["stale_reason"] = reason[:160]


_refreshing: set[str] = set()
_lock = threading.Lock()


def refresh_async(run_id: str) -> bool:
    """Rebuild the brief in the background. One refresh per run at a time;
    a second request while one is running is coalesced into it."""
    with _lock:
        if run_id in _refreshing:
            return False
        _refreshing.add(run_id)

    def _go():
        try:
            write_brief(run_id)
        except Exception as e:
            print(f"[brief] refresh failed for {run_id}: {e}")
        finally:
            with _lock:
                _refreshing.discard(run_id)

    threading.Thread(target=_go, name=f"brief-{run_id}", daemon=True).start()
    return True
