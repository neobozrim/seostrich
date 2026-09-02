from __future__ import annotations

from .. import llm
from ..config import settings


# The model assigns keywords by INDEX rather than repeating their text.
#
# This is the fix for the node that has failed every full run of this project.
# Echoing ~72 keyword phrases back across 10 clusters is almost all of the
# output, and output tokens are what cost time: measured generation speed is
# ~37 tok/s, so a 4500-token budget needs ~121s against a 120s client timeout.
# The call was arithmetically guaranteed to time out whenever the model used
# its budget. Indices cut the output several-fold, and the node also gets a
# timeout with real headroom.
SYSTEM_PROMPT = """You are an SEO content strategist. Group the numbered keywords into
thematic clusters by search intent and topic similarity.

You are given keywords as a numbered list. Refer to each keyword by its NUMBER.
Never write keyword text in your output — only numbers. This keeps your reply short.

Output JSON, and nothing else:
{
  "clusters": [
    {
      "id": 1,
      "name": "short descriptive cluster name",
      "head": 12,
      "kw": [12, 4, 19, 27],
      "intent": "informational|commercial|transactional",
      "why": "one short sentence, max 10 words"
    }
  ]
}

Rules:
- Produce exactly the number of clusters requested.
- When asked for 8 or more, OVER-GENERATE: capture more themes than will be
  pursued. A later step selects the strong ones — do not pre-filter here.
- 3-15 keywords per cluster. Every keyword belongs to at most one cluster.
- "head" is the cluster's primary keyword number (highest volume, most specific).
- Separate informational from commercial/transactional intent.
- "why" must be ONE short sentence. Never longer."""


def _resolve(ref, ranked: list[dict]) -> str | None:
    """Map a model reference (index or literal string) back to a keyword."""
    if isinstance(ref, bool):
        return None
    if isinstance(ref, int):
        return ranked[ref - 1].get("keyword") if 1 <= ref <= len(ranked) else None
    if isinstance(ref, str):
        text = ref.strip()
        if text.isdigit():
            i = int(text)
            return ranked[i - 1].get("keyword") if 1 <= i <= len(ranked) else None
        # Model ignored the instruction and wrote the phrase — accept it if real.
        lookup = {k.get("keyword", "").lower(): k.get("keyword") for k in ranked}
        return lookup.get(text.lower(), text) if text else None
    return None


# A head term with more words than this is a sentence, not a search. Seen
# 2026-09-01: the model chose "hugging face the ai community building the
# future" — a Hugging Face tagline — as the head of a cluster, and the cluster
# was then named and judged by it.
HEAD_MAX_WORDS = 5


def _pick_head(members: list[str], stats: dict) -> str:
    """The cluster's head term, chosen from the data rather than by the model.

    Highest volume wins. Among ties, the shortest phrase: it is the most
    generic form of the query, and it is what SERP verification and
    re-research key off. A phrase over HEAD_MAX_WORDS only wins if nothing
    shorter has any volume at all — a tagline should never front a cluster
    while a real query sits beside it.
    """
    def key(m: str):
        vol = stats.get(m.lower(), {}).get("volume") or 0
        words = len(m.split())
        return (-vol, words > HEAD_MAX_WORDS, words, m.lower())

    short = [m for m in members if len(m.split()) <= HEAD_MAX_WORDS]
    short_with_vol = [m for m in short if (stats.get(m.lower(), {}).get("volume") or 0) > 0]
    pool = short_with_vol or short or members
    return sorted(pool, key=key)[0]


def _expand(raw, ranked: list[dict]) -> list[dict]:
    """Turn index-based clusters into the full shape the pipeline expects."""
    clusters = raw.get("clusters") if isinstance(raw, dict) else raw
    if not isinstance(clusters, list):
        return []

    stats = {k.get("keyword", "").lower(): k for k in ranked}
    out: list[dict] = []
    for i, c in enumerate(clusters, 1):
        if not isinstance(c, dict):
            continue
        members = [
            kw for kw in (_resolve(r, ranked) for r in (c.get("kw") or c.get("keywords") or []))
            if kw
        ]
        if not members:
            continue
        vols = [stats.get(m.lower(), {}).get("volume") or 0 for m in members]
        head = _pick_head(members, stats)
        diffs = [stats.get(m.lower(), {}).get("difficulty") or 0 for m in members]
        out.append({
            "cluster_id": c.get("id", i),
            "cluster_name": c.get("name") or c.get("cluster_name") or f"Cluster {i}",
            "head_term": head,
            "keywords": members,
            "intent": c.get("intent", "informational"),
            "avg_volume": round(sum(vols) / len(vols)) if vols else 0,
            "avg_difficulty": round(sum(diffs) / len(diffs)) if diffs else 0,
            "rationale": c.get("why") or c.get("rationale") or "",
        })
    return out


def _diverse_top(keywords: list[dict], limit: int) -> list[dict]:
    """Pick `limit` keywords keeping coverage across the seeds that found them.

    Taking the top `limit` by volume alone let one seed's expansion swallow the
    whole slate. Observed 2026-09-01: "AI product manager" expanded into jobs,
    salary and certification terms at 700-3600 volume, while the topics the
    business is actually about sat at 10-140 and fell outside the cut — so the
    clusters described a job board. Round-robin across source seeds first
    (each seed's own keywords still ordered by volume), then fill any
    remaining slots by raw volume.
    """
    buckets: dict[str, list[dict]] = {}
    for kw in keywords:
        buckets.setdefault(kw.get("source_seed") or "", []).append(kw)
    for rows in buckets.values():
        rows.sort(key=lambda k: k.get("volume") or 0, reverse=True)

    picked: list[dict] = []
    seen: set[str] = set()
    if len(buckets) > 1:
        for i in range(max(len(r) for r in buckets.values())):
            for rows in buckets.values():
                if i >= len(rows) or len(picked) >= limit:
                    continue
                key = (rows[i].get("keyword") or "").lower()
                if key and key not in seen:
                    seen.add(key)
                    picked.append(rows[i])
            if len(picked) >= limit:
                break

    for kw in sorted(keywords, key=lambda k: k.get("volume") or 0, reverse=True):
        if len(picked) >= limit:
            break
        key = (kw.get("keyword") or "").lower()
        if key and key not in seen:
            seen.add(key)
            picked.append(kw)

    picked.sort(key=lambda k: k.get("volume") or 0, reverse=True)
    return picked


def cluster_keywords(
    keywords: list[dict],
    max_clusters: int = 10,
    location_code: int | None = None,
    language_code: str | None = None,
) -> dict:
    """Cluster keywords into thematic groups."""
    ranked = _diverse_top(keywords, 80)
    if not ranked:
        return {"success": False, "error": "no keywords to cluster", "clusters": None}

    kw_text = "\n".join(
        f"{i}. {k.get('keyword', '')} (vol {k.get('volume', 0)}, "
        f"kd {k.get('difficulty', 0)}, {k.get('intent', 'unknown')})"
        for i, k in enumerate(ranked, 1)
    )

    market_line = ""
    if location_code:
        market_line = f"\nTarget market: location_code {location_code}"
        if language_code:
            market_line += f", language {language_code}"
        market_line += "."

    user_msg = (
        f"Keywords (refer to these by number):\n{kw_text}\n{market_line}\n"
        f"Create {max_clusters} thematic clusters. Use keyword NUMBERS only in "
        f"\"kw\" and \"head\". Keep every \"why\" to one short sentence."
    )

    try:
        # Grouping keywords is mechanical, so run it on the fast model: same ten
        # clusters in 44s instead of 254s, because the reasoning model spends
        # ~9.5k thinking tokens it does not need here.
        resp = llm.chat(
            user_msg, system=SYSTEM_PROMPT, temperature=0.3,
            max_tokens=2500, model=settings.qwen_model_fast,
        )
        parsed = llm.parse_json_response(resp)
        clusters = _expand(parsed, ranked)
        if clusters:
            return {"success": True, "clusters": clusters}
        return {"success": False, "error": "LLM returned invalid cluster format", "clusters": None}
    except Exception as e:
        return {"success": False, "error": f"LLM clustering failed: {str(e)}", "clusters": None}
