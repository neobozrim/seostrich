# How SEOstrich works — the three graphs

Every step below is code, not a prompt: the order and the gates are fixed, every
node records its output as a stage on the artefact, and the only thing a model
decides is wording and grouping. Paid DataForSEO calls are marked 💰; model
calls are marked 🤖; everything else is arithmetic.

## 1. The system

```mermaid
flowchart LR
  U([You]) --> UI[SEOstrich<br/>artefact-first UI]
  A([Your own assistant<br/>ChatGPT · Chrome]) -- "WebMCP · 22 tools" --> UI
  UI --> O[Orchestrator<br/>routes the request<br/>never edits a result]
  O --> SEO[SEO agent<br/>runs the enforced graphs<br/>then reads and reports]
  O --> BR[Brand agent<br/>identity · voice · naming]
  SEO --> SG[[Strategy graph]]
  SEO --> GG[[GEO graph]]
  SG --> DFS[(DataForSEO)]
  GG --> DFS
  SG --> LLM[(OpenAI · Qwen)]
  GG --> LLM
  SG --> ST[(Artefacts<br/>stages · governance log · brief)]
  GG --> ST
  ST --> UI
  UI -- "promote · discard · propose · reset · rebuild" --> ST
  A -- "same tools, same artefact" --> ST
```

The orchestrator only routes. The SEO agent runs a graph and reports on it; after
a graph returns, the tools that change the selection are removed from its turn.
Changing the selection is the person's job — in the UI or through their own
assistant over WebMCP — and every change is logged with who and why.

## 2. The strategy graph (`run_keyword_strategy`)

```mermaid
flowchart TD
  IN([Brief + every URL in it]) --> M{Confirm market<br/>country + language<br/>never inferred from the domain}
  M --> RP[Read your own pages<br/>site · blog · guarded fetch]
  RP --> S[🤖 Seeds<br/>from the brief and what your pages say]
  S --> EXP[💰 Expand seeds<br/>related · suggestions]
  CMP[💰 Competitors<br/>what each ranks for] --> BF[Brand filter<br/>their own name is not a topic]
  BF --> RG[🤖 Relevance gate<br/>is this YOUR topic?]
  RG --> BAL[Balance<br/>never more than your own seeds]
  EXP --> UNI[(Keyword universe<br/>volume · KD · CPC · intent · owner)]
  BAL --> UNI
  UNI --> CL[🤖 Cluster into themes<br/>over-generate 10 · fast model]
  CL --> SV[💰 SERP-overlap verify<br/>same top-10 ⇒ one page]
  SV --> VG{Validation gate<br/>coherent?}
  VG --> MET[Measure each theme<br/>arithmetic on the rows]
  MET --> DF{Demand floor<br/>best keyword ≥ 20/mo<br/>waived in thin markets}
  DF --> SEL[🤖 Select 3–4 for THIS business<br/>reasons on both sides of the cut]
  SEL --> PIL[🤖 Content pillars]
  PIL --> BRF[🤖 The brief<br/>the call · who to out-answer<br/>6 pieces · what was parked]
  BRF --> ART[(Artefact)]
  ART <-- "governance, logged" --> WM([You, or your assistant over WebMCP])
```

## 3. The GEO graph (`run_geo_demand`)

```mermaid
flowchart TD
  IN([Topics + market]) --> M{Confirm market}
  M --> DM[💰 Search demand per topic<br/>one call for all]
  DM --> SL[Shortlist<br/>only what has demand goes further]
  SL --> CI[💰 AI citability<br/>which questions AI already answers<br/>who is cited · AI search volume]
  CI --> DP[💰 Displaceability<br/>authority of the cited sites<br/>open share = citable sources below the giants]
  DP --> RK[Rank on measured evidence<br/>demand × open share]
  RK --> PAA[💰 People-also-ask<br/>winners only]
  PAA --> PLAN[🤖 Answer-first content plan<br/>the question is the heading<br/>the first two sentences are the answer]
  PLAN --> ART[(Artefact)]
  PLAN -.-> DOM[💰 Optional: which AI answers<br/>already cite your site]
```
