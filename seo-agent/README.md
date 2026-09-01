# SEOstrich

An SEO agent that shows its work — and lets *your* AI assistant steer it.

Most SEO tools hand you a report. SEOstrich runs the research as an enforced
graph, records every step as an inspectable artifact, and exposes the whole
thing over **WebMCP** so an agent in your browser can read the data, argue with
a decision, and ask for work to be redone.

## Why WebMCP here

An SEO strategy is a chain of judgement calls — which market, which keywords
matter, which clusters are worth pursuing, which topics you could realistically
win. Every one of those is a place a human (or their agent) may reasonably
disagree with the machine.

So the pipeline does not just publish results. It publishes **the reasoning
behind each decision**, and the operations to change it:

- `seo_list_clusters_all` — every cluster, selected *and* discarded, each with a
  `reasoning` block: why it was kept or dropped, why those keywords group
  together, and metrics measured from real data rather than estimated.
- `seo_promote_cluster` / `seo_discard_cluster` — disagree with the cut. Read
  the stated reason first, then override it. Fully reversible.
- `seo_propose_cluster` — add a topic the pipeline never explored; it runs real
  keyword research on it.
- `seo_rerun_cluster_research` — refresh one cluster without re-running (or
  re-billing) the rest.
- `seo_get_keywords` — the flat keyword table with volume, difficulty, CPC and
  intent, so a visiting agent can do its own analysis instead of trusting ours.
- `seo_check_ai_citations` — which AI answers already cite a domain. Point it at
  your own site for a baseline, or at a competitor to see what they get quoted
  for.

Seventeen tools in total, each documented with what it returns, when to reach
for it, and whether it spends money.

## The flows

**Content strategy** — seeds → keyword universe → clusters → validation gate →
scoring → selection → AI-citability → content pillars.

**AI visibility (GEO)** — measure real search demand, check which AI answers
exist and who they cite, grade whether those sites can realistically be
displaced, then harvest the actual questions people ask *only* for the topics
that earned it.

`reverse_strategy` and `technical_audit` are declared but not yet built; the UI
says so rather than letting the agent improvise a half-flow.

## Two principles the code enforces

**The market is never inferred.** A `.bg` domain does not mean the business
targets Bulgaria in Bulgarian — plenty of people sell from a local TLD into a
different market entirely. The pipeline refuses to start until the user has
stated the country *and* language.

**Measured, not estimated.** Cluster metrics are computed from the DataForSEO
rows, not guessed by a model. An earlier version asked an LLM for 0-100 "SEO
scores"; it rated a 670-volume cluster above a 4,360-volume one. Numbers now
come from arithmetic, and every input is published so you can re-rank on
whichever metric you care about.

## Running it

```bash
# backend
pip install -r requirements.txt
python -m uvicorn api.main:app --port 8001

# frontend
cd ui && npm install && npm run dev
```

Copy `.env.example` to `../.env` and fill in DataForSEO credentials and a Qwen
API key. Set `USER_NAME` / `PASSWORD` to require login; leave them unset and the
app stays open (useful locally, not in public).

Tests are standalone scripts — `python tests_geo.py`, `python tests_market.py`
and so on. Each prints its assertions and exits non-zero on failure.

## Licence

MIT — see [LICENSE](../LICENSE).
