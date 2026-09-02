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

from ..pipeline_recorder import use_run

from .. import llm, runs
from ..config import settings
from . import dataforseo as dfs

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
      "question": "the question this piece answers — VERBATIM from the cluster's observed_questions when it has any",
      "question_source": "people_also_ask | written",
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
- Exactly 6 pieces. Every selected cluster gets at least one; no cluster gets more than 3,
  however large it is — a strategy is not six articles about one tool;
  every piece's target_keyword must be a keyword from the input.
- Each selected cluster lists observed_questions: the questions Google itself shows
  under that cluster's head term (People also ask), with the domain currently answering
  each. When a cluster has any, every piece for that cluster takes its question VERBATIM
  from that list and sets question_source to "people_also_ask". Only when the list is
  empty may you write the question yourself; then set question_source to "written".
  Never paraphrase an observed question.
- No two pieces answer the same question. Six pieces, six different questions.
- The question is the heading a reader searches for; the first two sentences under it
  must be able to answer it.
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


def _norm_q(q: str) -> str:
    return " ".join(str(q or "").lower().replace("?", "").split())


def observe_questions(inp: dict, run_id: str, location_code: int, language_code: str) -> dict:
    """Ask Google what people ask. One SERP call per selected cluster, on its
    head term (the top keyword when the head term shows nothing). The result
    goes into the input the model sees, so a piece's question can be a
    question people actually search for rather than one the model made up.
    Fails open: no questions means the model writes them and says so."""
    observed: dict[str, int] = {}
    for c in inp["selected_clusters"]:
        terms = []
        if c.get("head_term"):
            terms.append(c["head_term"])
        top = next((k["keyword"] for k in c["keywords"] if k.get("keyword")), None)
        if top and top not in terms:
            terms.append(top)
        qs: list[dict] = []
        for term in terms[:2]:
            try:
                with use_run(run_id):
                    rows = dfs.serp_paa(term, location_code=location_code, language_code=language_code)
            except Exception as e:  # budget, network, parsing — the brief still gets written
                print(f"[brief] people-also-ask for {term!r} skipped: {str(e)[:120]}")
                rows = []
            for r in rows or []:
                q = (r.get("question") or "").strip()
                if q and _norm_q(q) not in {_norm_q(x["question"]) for x in qs}:
                    qs.append({"question": q, "asked_under": term, "answered_by": r.get("domain") or ""})
            if qs:
                break
        c["observed_questions"] = qs[:10]
        observed[c["cluster"]] = len(c["observed_questions"])
    return observed


def _tag_questions(pieces: list[dict], inp: dict) -> None:
    """Deterministic provenance on every piece: observed or written. The
    model's own question_source is not trusted; the match decides."""
    by_cluster = {c["cluster"]: c.get("observed_questions") or [] for c in inp["selected_clusters"]}
    for pc in pieces:
        hit = next((q for q in by_cluster.get(pc.get("cluster"), []) if _norm_q(q["question"]) == _norm_q(pc.get("question"))), None)
        if hit:
            pc["question_source"] = "people_also_ask"
            pc["asked_under"] = hit["asked_under"]
            pc["currently_answered_by"] = str(hit.get("answered_by") or "").removeprefix("www.")
        else:
            pc["question_source"] = "written"
            pc.pop("asked_under", None)
            pc.pop("currently_answered_by", None)


def _who_answers(pieces: list[dict], run_id: str, location_code: int, language_code: str) -> None:
    """The page that answers each question today, from a live SERP on the
    question itself: one call per piece, top organic result. People-also-ask
    stopped carrying sources (its expansion is an AI overview now), and a
    brief that says "answer this better than X" needs a real X. Fails open."""
    for pc in pieces:
        if pc.get("currently_answered_by") or not pc.get("question"):
            continue
        try:
            with use_run(run_id):
                rows = dfs.serp_organic(pc["question"], location_code=location_code, language_code=language_code, depth=3)
        except Exception as e:
            print(f"[brief] who-answers for {pc['question'][:50]!r} skipped: {str(e)[:100]}")
            continue
        top = next((r for r in rows or [] if r.get("domain")), None)
        if top:
            pc["currently_answered_by"] = str(top["domain"]).removeprefix("www.")
            pc["answered_by_url"] = top.get("url") or ""
            pc["answered_by_source"] = "serp"


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
    seen_q: set[str] = set()
    for p in pieces:
        if not (isinstance(p, dict) and p.get("title") and p.get("question")):
            return False, "a piece lacks title or question"
        if _norm_q(p["question"]) in seen_q:
            return False, f"two pieces answer the same question: {p['question'][:80]!r}"
        seen_q.add(_norm_q(p["question"]))
        tk = str(p.get("target_keyword") or "").lower()
        if known and tk and tk not in known:
            return False, f"target_keyword not in input: {tk}"
        observed = next((c.get("observed_questions") or [] for c in inp["selected_clusters"] if c["cluster"] == p.get("cluster")), [])
        if observed and _norm_q(p["question"]) not in {_norm_q(q["question"]) for q in observed}:
            return False, f"the question for {p.get('cluster')!r} is not one of its observed_questions (use one verbatim): {p['question'][:80]!r}"
    # Spread: a strategy is not six articles about one tool. Every selected
    # cluster gets a piece and none gets more than three.
    per_cluster: dict[str, int] = {}
    for p in pieces:
        if p.get("cluster"):
            per_cluster[p["cluster"]] = per_cluster.get(p["cluster"], 0) + 1
    selected_names = [c["cluster"] for c in inp["selected_clusters"] if c.get("cluster")]
    if len(selected_names) >= 2 and len(pieces) >= len(selected_names):
        missing = [n for n in selected_names if n not in per_cluster]
        if missing:
            return False, f"every selected cluster gets at least one piece; none for {missing[0]!r}"
        heavy = [n for n, k in per_cluster.items() if k > 3]
        if heavy:
            return False, f"no cluster gets more than 3 of the pieces; {heavy[0]!r} has {per_cluster[heavy[0]]}"
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
    locale = next((s.get("artifact", {}).get("locale") or {} for s in run.get("stages", []) if s.get("id") == "intake"), {})
    questions_observed = observe_questions(inp, run_id, locale.get("location_code") or 2840, locale.get("language_code") or "en")

    user_msg = f"Write the brief.\n\n{llm.format_json(inp)}"
    last_err = ""
    brief = None
    for attempt in range(2):
        try:
            resp = llm.chat(user_msg if attempt == 0 else user_msg + f"\n\nYour previous answer was rejected: {last_err}. Fix it.",
                            system=SYSTEM_PROMPT, model=settings.model_fast, temperature=0.2, max_tokens=2500)
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
    _tag_questions(pieces, inp)
    _who_answers(pieces, run_id, locale.get("location_code") or 2840, locale.get("language_code") or "en")
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
            "questions_observed": questions_observed,
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
