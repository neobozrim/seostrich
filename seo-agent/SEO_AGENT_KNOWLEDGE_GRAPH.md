# SEO Agent System - Knowledge Graph

## 1. System Architecture Overview

```mermaid
graph TB
    subgraph "User Interface"
        User[User Request]
    end

    subgraph "Orchestrator Layer"
        Orchestrator[Orchestrator<br/>Planning + Routing]
        PlanGen[Plan Generator<br/>Intent Classification]
        ToolSelector[Tool Selector<br/>Category-Based]
        
        User --> Orchestrator
        Orchestrator --> PlanGen
        Orchestrator --> ToolSelector
    end

    subgraph "Specialist Agents"
        SEO[SEO Agent<br/>55 tools<br/>max 20 rounds]
        Brand[Brand Agent<br/>10 tools<br/>max 30 rounds]
        Builder[Builder Agent<br/>11 tools<br/>max 50 rounds]
        Monitor[Monitoring Agent<br/>13 tools<br/>max 20 rounds]
        
        Orchestrator --> SEO
        Orchestrator --> Brand
        Orchestrator --> Builder
        Orchestrator --> Monitor
    end

    subgraph "Shared Memory Blackboard"
        Memory[Memory System<br/>2-Pass Synthesis]
        Facts[Facts]
        Learnings[Learnings]
        Decisions[Decisions]
        BrandConstraints[Brand Constraints]
        Tasks[Tasks]
        Artefacts[Artefacts]
        
        Memory --> Facts
        Memory --> Learnings
        Memory --> Decisions
        Memory --> BrandConstraints
        Memory --> Tasks
        Memory --> Artefacts
    end

    SEO -.-> Memory
    Brand -.-> Memory
    Builder -.-> Memory
    Monitor -.-> Memory

    subgraph "External APIs"
        Qwen[Qwen LLM API]
        DataForSEO[DataForSEO API]
        GSC[Google Search Console]
        PageSpeed[PageSpeed API]
        Bing[Bing Webmaster Tools]
        Braintrust[Braintrust Tracing]
        
        SEO --> Qwen
        SEO --> DataForSEO
        SEO --> GSC
        SEO --> PageSpeed
        Monitor --> GSC
        Monitor --> DataForSEO
        Brand --> Qwen
        Builder --> Qwen
    end

    SEO -.-> Braintrust
    Brand -.-> Braintrust
    Builder -.-> Braintrust
    Monitor -.-> Braintrust

    style Orchestrator fill:#e1f5ff
    style SEO fill:#fff4e1
    style Brand fill:#f4e1ff
    style Builder fill:#e1ffe1
    style Monitor fill:#ffe1e1
    style Memory fill:#f0f0f0
```

---

## 2. SEO Agent Tool Categories

```mermaid
graph LR
    subgraph "Audit Tools (16)"
        A1[audit_crawlability]
        A2[audit_meta_tags]
        A3[audit_structured_data]
        A4[audit_performance]
        A5[audit_mobile]
        A6[audit_i18n]
        A7[audit_content]
        A8[render_and_compare]
        A9[technical_seo_audit<br/>LEGACY]
        A10[validate_sitemap]
        A11[check_redirects]
        A12[internal_link_audit]
        A13[duplicate_content_scan]
        A14[hreflang_validator]
        A15[content_freshness_scan]
        A16[pagination_audit]
    end

    subgraph "Content Tools (5)"
        C1[generate_draft<br/>E-E-A-T + brand voice]
        C2[preflight_draft<br/>E-E-A-T assessment]
        C3[seo_linter<br/>E-E-A-T scoring]
        C4[geo_scorer<br/>AI citation potential]
        C5[content_quality_assessment]
    end

    subgraph "Research Tools (14)"
        R1[extract_seeds]
        R2[pull_universe<br/>DataForSEO]
        R3[cluster_keywords]
        R4[validate_clusters<br/>🔴 MANDATORY GATE]
        R5[score_clusters]
        R6[recommend_pillars]
        R7[serp_organic]
        R8[serp_ai_mode]
        R9[keyword_difficulty]
        R10[historical_search_volume]
        R11[competitors_domain]
        R12[domain_intersection]
        R13[keywords_for_site]
        R14[web_search]
    end

    subgraph "Strategy Tools (2)"
        S1[plan_calendar]
        S2[run_discovery]
    end

    subgraph "GSC Tools (5)"
        G1[gsc_performance]
        G2[gsc_inspect_url]
        G3[gsc_list_sitemaps]
        G4[gsc_list_sites]
        G5[gsc_submit_sitemap]
    end

    subgraph "Indexing Tools (3)"
        I1[submit_indexnow]
        I2[submit_single_url]
        I3[bing_submit_url]
    end

    subgraph "Monitoring (1)"
        M1[ai_mentions]
    end

    subgraph "Memory Tools (6)"
        MEM1[read_memory]
        MEM2[record_fact]
        MEM3[record_learning]
        MEM4[record_decision]
        MEM5[record_artefact]
        MEM6[draft_run_summary]
    end

    subgraph "Meta Tools (3)"
        META1[log_conversation]
        META2[suggest_improvements]
        META3[execute_with_fallback]
    end

    style R4 fill:#ffcccc
    style A9 fill:#ffffcc
```

---

## 3. Keyword Research Workflow with Reflection Gate

```mermaid
sequenceDiagram
    participant User
    participant Orchestrator
    participant SEO
    participant Tools
    participant LLM
    participant Memory

    User->>Orchestrator: "Do keyword research for my SaaS"
    Orchestrator->>LLM: Generate execution plan
    LLM-->>Orchestrator: Plan: discovery → seeds → universe → cluster → validate → score → pillars → calendar
    
    Note over Orchestrator,User: Stream plan to user (no confirmation needed)
    Orchestrator->>User: 📋 Plan displayed
    
    Orchestrator->>SEO: Route to SEO agent
    
    SEO->>Tools: run_discovery()
    Tools-->>SEO: Business context
    
    SEO->>Tools: extract_seeds()
    Tools-->>SEO: Seed keywords
    
    SEO->>Tools: pull_universe()
    Note over Tools: DataForSEO API
    Tools-->>SEO: Expanded keyword universe
    
    SEO->>Tools: cluster_keywords()
    Tools-->>SEO: Keyword clusters
    
    rect rgb(255, 220, 220)
        Note over SEO,LLM: MANDATORY REFLECTION GATE
        SEO->>Tools: validate_clusters(clusters)
        Note over Tools: LLM evaluates coherence
        Tools-->>SEO: Verdict + issues
        
        alt Verdict = "needs_revision"
            SEO->>Tools: cluster_keywords() with adjusted params
            Tools-->>SEO: New clusters
            SEO->>Tools: validate_clusters(new_clusters)
            Tools-->>SEO: Re-evaluate
        else Verdict = "rejected"
            SEO->>Tools: cluster_keywords() with different approach
            Tools-->>SEO: Different clusters
            SEO->>Tools: validate_clusters(different_clusters)
            Tools-->>SEO: Re-evaluate
        end
    end
    
    Note over SEO: Only proceed if verdict = "approved"
    
    SEO->>Tools: score_clusters(validated_clusters)
    Tools-->>SEO: Opportunity scores
    
    SEO->>Tools: recommend_pillars(scored_clusters)
    Tools-->>SEO: Strategic pillars
    
    SEO->>Tools: plan_calendar(pillars)
    Tools-->>SEO: Content calendar
    
    SEO->>Memory: record_decision(pillars + calendar)
    
    SEO-->>Orchestrator: Keyword strategy complete
    Orchestrator-->>User: Present strategy + calendar
```

---

## 4. Audit Workflow with Composable Tools

```mermaid
sequenceDiagram
    participant User
    participant Orchestrator
    participant ToolSelector
    participant SEO
    participant Tools
    participant LLM

    User->>Orchestrator: "Audit mysite.com for SEO"
    
    Orchestrator->>ToolSelector: Classify intent
    Note over ToolSelector: "audit" keyword detected
    ToolSelector-->>Orchestrator: Load audit + memory categories (22 tools)
    
    Orchestrator->>SEO: Route with filtered tools
    
    rect rgb(220, 240, 255)
        Note over SEO,Tools: Round 0: Parallel Composable Audits
        SEO->>Tools: audit_crawlability()
        SEO->>Tools: audit_meta_tags()
        SEO->>Tools: audit_structured_data()
        SEO->>Tools: audit_performance()
        SEO->>Tools: audit_mobile()
        SEO->>Tools: audit_content()
        Tools-->>SEO: 6 audit results
    end
    
    SEO->>LLM: Synthesize findings
    LLM-->>SEO: Identify areas needing deeper analysis
    
    rect rgb(255, 240, 220)
        Note over SEO,Tools: Round 1: Deep Dive on Issues
        alt hreflang issues found
            SEO->>Tools: audit_i18n()
        end
        alt JS rendering concerns
            SEO->>Tools: render_and_compare()
        end
        alt sitemap present
            SEO->>Tools: validate_sitemap()
        end
        Tools-->>SEO: Detailed findings
    end
    
    rect rgb(220, 255, 220)
        Note over SEO,Tools: Round 2: Specialized Analysis
        alt internal link issues
            SEO->>Tools: internal_link_audit()
        end
        alt duplicate content suspected
            SEO->>Tools: duplicate_content_scan()
        end
        alt redirect chains detected
            SEO->>Tools: check_redirects()
        end
        Tools-->>SEO: Specialized findings
    end
    
    SEO->>LLM: Generate structured report
    LLM-->>SEO: Executive Summary + Issues + Recommendations
    
    SEO-->>Orchestrator: Comprehensive audit report
    Orchestrator-->>User: Present findings
```

---

## 5. Fallback Chain Topology

```mermaid
graph LR
    subgraph "Fallback Chains"
        direction TB
        
        GSC[gsc_performance] -->|GSC API fails| Bing[get_site_keywords<br/>Bing WMT data]
        
        Legacy[technical_seo_audit] -->|Monolithic fails| Crawl[audit_crawlability]
        Legacy -->|or| Meta[audit_meta_tags]
        
        DFS[DataForSEO Tools] -.->|NO FALLBACK| X[Report error + retry<br/>web_search ≠ keyword data]
    end

    style DFS fill:#ffcccc
    style X fill:#ffcccc
    style GSC fill:#e1f5ff
    style Bing fill:#e1f5ff
    style Legacy fill:#ffffcc
    style Crawl fill:#e1ffe1
    style Meta fill:#e1ffe1
```

---

## 6. Memory System Architecture

```mermaid
graph TB
    subgraph "Memory Blackboard"
        direction TB
        Facts[Facts<br/>Objective data points]
        Learnings[Learnings<br/>Insights from execution]
        Decisions[Decisions<br/>Strategic choices]
        BrandConstraints[Brand Constraints<br/>Voice, tone, rules]
        Tasks[Tasks<br/>Work tracking]
        Artefacts[Artefacts<br/>Generated outputs]
        RunSummaries[Run Summaries<br/>Session outcomes]
    end

    subgraph "Memory Operations"
        Read[read_memory<br/>Query + filter]
        RecordFact[record_fact]
        RecordLearning[record_learning]
        RecordDecision[record_decision]
        RecordArtefact[record_artefact]
        DraftSummary[draft_run_summary]
    end

    subgraph "Synthesis Pipeline"
        Extract[Extract Phase<br/>LLM identifies candidates]
        QualityGate[Quality Gates<br/>Specificity + Stability]
        Critique[Self-Critique Phase<br/>Validate candidates]
        Merge[Merge to Files]
        Compress[Compress Old Entries<br/>Archive after 90 days]
    end

    subgraph "External Tracing"
        Braintrust[Braintrust API<br/>Hierarchical traces]
        SessionStore[Session JSON<br/>Full conversation history]
        TracesCache[Traces Cache<br/>Local trace storage]
    end

    Facts --- Read
    Learnings --- Read
    Decisions --- Read
    BrandConstraints --- Read
    Tasks --- Read
    Artefacts --- Read

    RecordFact --> Facts
    RecordLearning --> Learnings
    RecordDecision --> Decisions
    RecordArtefact --> Artefacts
    DraftSummary --> RunSummaries

    Extract --> QualityGate
    QualityGate --> Critique
    Critique --> Merge
    Merge --> Compress

    Learnings --> Extract
    Facts --> Extract
    Decisions --> Extract

    SessionStore --> Braintrust
    Braintrust --> TracesCache
    TracesCache --> Extract

    style BrandConstraints fill:#f4e1ff
    style Braintrust fill:#ffe1e1
```

---

## 7. Agent Communication via Memory

```mermaid
sequenceDiagram
    participant User
    participant Orchestrator
    participant Brand
    participant SEO
    participant Builder
    participant Memory

    User->>Orchestrator: "Create brand + SEO strategy + build site"
    
    Orchestrator->>Brand: Route brand identity task
    Brand->>Memory: record_decision(brand_palette, typography, voice)
    Brand->>Memory: record_artefact(brand_profile.json)
    Brand-->>Orchestrator: Brand identity complete
    
    Orchestrator->>SEO: Route keyword research
    SEO->>Memory: read_memory(filter=brand)
    Memory-->>SEO: Brand constraints loaded
    Note over SEO: Generate content aligned with brand voice
    SEO->>Memory: record_decision(pillars aligned with brand)
    SEO->>Memory: record_artefact(content_calendar.json)
    SEO-->>Orchestrator: Strategy complete
    
    Orchestrator->>Builder: Route site build
    Builder->>Memory: read_memory(filter=brand)
    Memory-->>Builder: Brand constraints loaded
    Builder->>Memory: read_memory(filter=artefacts)
    Memory-->>Builder: Brand profile + content calendar loaded
    Note over Builder: Implement site using brand tokens + content plan
    Builder->>Memory: record_artefact(site.html)
    Builder-->>Orchestrator: Site built
    
    Orchestrator-->>User: Complete: brand + strategy + site
```

---

## 8. Tool Selection Flow

```mermaid
graph TB
    UserQuery[User Query] --> Classifier[Intent Classifier<br/>Keyword Matching]
    
    Classifier --> Audit{Contains audit keywords?}
    Classifier --> Content{Contains content keywords?}
    Classifier --> Research{Contains research keywords?}
    Classifier --> GSC{Contains GSC keywords?}
    Classifier --> Indexing{Contains indexing keywords?}
    Classifier --> Monitoring{Contains monitoring keywords?}
    
    Audit -->|Yes| LoadAudit[Load Audit Category<br/>16 tools]
    Content -->|Yes| LoadContent[Load Content Category<br/>5 tools]
    Research -->|Yes| LoadResearch[Load Research Category<br/>14 tools]
    GSC -->|Yes| LoadGSC[Load GSC Category<br/>5 tools]
    Indexing -->|Yes| LoadIndexing[Load Indexing Category<br/>3 tools]
    Monitoring -->|Yes| LoadMonitoring[Load Monitoring Category<br/>1 tool]
    
    LoadAudit --> AlwaysMemory
    LoadContent --> AlwaysMemory
    LoadResearch --> AlwaysMemory
    LoadGSC --> AlwaysMemory
    LoadIndexing --> AlwaysMemory
    LoadMonitoring --> AlwaysMemory
    
    None{Any category matched?}
    Classifier --> None
    
    None -->|No| LoadAll[Load ALL Tools<br/>55 tools<br/>Fallback for ambiguous queries]
    
    AlwaysMemory[Always Load Memory<br/>6 tools] --> ToolSet[Final Tool Set<br/>22-55 tools]
    LoadAll --> ToolSet
    
    ToolSet --> LLM[Send to LLM<br/>Reduced context window]
    
    style LoadAll fill:#ffffcc
    style AlwaysMemory fill:#e1f5ff
```

---

## 9. Post-Loop Synthesis Flow

```mermaid
graph TB
    ToolLoop[Tool Execution Loop] --> CheckLast{Last message<br/>is planning text?}
    
    CheckLast -->|No| End[Session Complete<br/>Natural ending]
    CheckLast -->|Yes| Detect[Detect Planning Indicators<br/>"let me", "now let's", etc.]
    
    Detect --> HasFindings{Contains findings<br/>keywords?}
    
    HasFindings -->|Yes| End
    HasFindings -->|No| Synthesis[Post-Loop Synthesis]
    
    Synthesis --> Condense[Condense Messages<br/>Extract key findings from tool results]
    Condense --> Truncate[Truncate to Top 5 Issues Per Tool]
    Truncate --> BuildPrompt[Build Synthesis Prompt<br/>Structured report template]
    
    BuildPrompt --> LLMSynthesis[LLM Generate Report]
    
    LLMSynthesis --> Success{Success?}
    Success -->|Yes| AddReport[Add Report to Session]
    Success -->|No| Fallback[Fallback: Basic Summary<br/>From tool results]
    
    AddReport --> Save[Save Session]
    Fallback --> Save
    End --> Save
    
    style Synthesis fill:#ffe1e1
    style Condense fill:#e1ffe1
    style Fallback fill:#ffffcc
```

---

## 10. Complete System Data Flow

```mermaid
graph TB
    subgraph "Input"
        UserRequest[User Request]
    end

    subgraph "Orchestrator"
        Planning[Planning Step<br/>Decompose Task]
        Intent[Intent Classification<br/>Select Agent]
        ToolSelect[Tool Selection<br/>Category-Based]
    end

    subgraph "SEO Agent"
        SEOLoop[Tool Execution Loop<br/>Max 20 rounds]
        SEOTools[55 Available Tools]
        SEOSynthesis[Post-Loop Synthesis<br/>If planning text detected]
    end

    subgraph "Brand Agent"
        BrandLoop[Tool Execution Loop<br/>Max 30 rounds]
        BrandTools[10 Available Tools]
    end

    subgraph "Builder Agent"
        BuilderLoop[Tool Execution Loop<br/>Max 50 rounds]
        BuilderTools[11 Available Tools]
        Tier1[Tier 1: Mechanical Check]
        Tier2[Tier 2: Compliance Check<br/>HARD GATE]
        Tier3[Tier 3: Judgment Assessment]
    end

    subgraph "Monitoring Agent"
        MonitorLoop[Tool Execution Loop<br/>Max 20 rounds]
        MonitorTools[13 Available Tools]
    end

    subgraph "Memory System"
        Blackboard[Shared Blackboard]
        Synthesis2Pass[2-Pass Synthesis<br/>Extract + Self-Critique]
        Compression[Compression<br/>Archive old entries]
    end

    subgraph "External Services"
        QwenAPI[Qwen LLM]
        DataForSEOAPI[DataForSEO]
        GSCAPI[Google Search Console]
        BraintrustAPI[Braintrust]
    end

    UserRequest --> Planning
    Planning --> Intent
    Intent --> ToolSelect
    
    ToolSelect --> SEOLoop
    ToolSelect --> BrandLoop
    ToolSelect --> BuilderLoop
    ToolSelect --> MonitorLoop
    
    SEOLoop --> SEOTools
    SEOTools --> SEOSynthesis
    SEOSynthesis --> Blackboard
    
    BrandLoop --> BrandTools
    BrandTools --> Blackboard
    
    BuilderLoop --> BuilderTools
    BuilderTools --> Tier1
    Tier1 --> Tier2
    Tier2 --> Tier3
    Tier3 --> Blackboard
    
    MonitorLoop --> MonitorTools
    MonitorTools --> Blackboard
    
    Blackboard --> Synthesis2Pass
    Synthesis2Pass --> Compression
    
    SEOLoop --> QwenAPI
    SEOLoop --> DataForSEOAPI
    SEOLoop --> GSCAPI
    MonitorLoop --> GSCAPI
    MonitorLoop --> DataForSEOAPI
    
    SEOLoop --> BraintrustAPI
    BrandLoop --> BraintrustAPI
    BuilderLoop --> BraintrustAPI
    MonitorLoop --> BraintrustAPI
    
    style SEOSynthesis fill:#ffe1e1
    style Tier2 fill:#ffcccc
    style Synthesis2Pass fill:#e1ffe1
```

---

## Legend

- **Blue nodes**: Core system components
- **Green nodes**: Successful operations / tools
- **Yellow nodes**: Legacy / fallback / warnings
- **Red nodes**: Critical gates / error handling
- **Purple nodes**: Brand-related components
- **Gray nodes**: Memory / storage

---

## Key Insights from Knowledge Graph

1. **Tool Selection Optimization**: Category-based selection reduces context from 55 to 22-27 tools for specific intents, improving LLM performance and reducing costs.

2. **Reflection Pattern**: The validate_clusters tool acts as a mandatory gate in the keyword research workflow, preventing "hallucinated strategy" from incoherent clusters.

3. **Composable vs Legacy**: The audit suite split provides 8 specialized tools that can be chained, while the legacy technical_seo_audit remains for backward compatibility.

4. **Memory as Communication Layer**: Agents don't communicate directly - they read/write to the shared blackboard, creating a decoupled architecture.

5. **Fallback Chains Limited**: Only non-data tools have fallbacks. DataForSEO tools have NO fallbacks because web_search cannot provide equivalent keyword/SERP data.

6. **Post-Loop Synthesis**: Detects when the agent stops with planning text and forces generation of a structured final report, preventing incomplete outputs.

7. **Parallel Tool Execution**: Multiple tools can be called in parallel within a single round, improving efficiency for independent operations.

8. **Planning Without Confirmation**: The orchestrator generates and displays a plan for transparency, but doesn't block execution on user confirmation (per research findings).

---

*Generated: 2026-07-28*  
*System Version: SEO Agent v2.0 (Post-Google Research + Andrew Ng Patterns Implementation)*
