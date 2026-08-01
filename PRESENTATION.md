# Claude Code Telemetry Analytics — Findings & Insights

## Executive Summary

Analysis of **454,428 telemetry events** (118K API requests, 300K tool events, 35K prompts, 1.4K errors) from 100 employees across 5 engineering practices reveals clear patterns in Claude Code adoption, cost drivers, and operational health opportunities.

---

## Key Findings

### 1. Cost Concentration

**A small number of model choices drive the majority of spend.**

- **Claude Opus models** (4.5 + 4.6) account for ~$4,258 total — the largest cost center despite representing ~42% of requests
- **Claude Sonnet models** (4.5 + 4.6) represent ~$1,558 — the mid-tier workhorse
- **Claude Haiku 4.5** handles the most requests (46K) at only ~$186 total — 95% cheaper per-request than Opus

**Recommendation**: Establish model-routing guidelines — use Haiku for routine operations (file reads, grep) and reserve Opus for complex multi-step reasoning. This could reduce total cost by 20-30% without impacting output quality.

### 2. Cache Utilization Is Strong but Uneven

- Overall cache read ratio is high, indicating effective prompt caching across sessions
- **Disparity across practices**: some teams show significantly lower cache utilization, suggesting different usage patterns or shorter sessions that don't benefit from caching

**Recommendation**: Share session best practices — longer, focused coding sessions yield better cache efficiency. Teams with lower ratios may benefit from workflow adjustments.

### 3. Tool Decision Patterns

- **Read** and **Edit** are the most frequently used tools across all practices
- Tool rejection rate is non-trivial — users actively override agent tool decisions, particularly for **Edit** operations
- **Bash** and **mcp_tool** show lower adoption but higher latency

**Recommendation**: Investigate Edit rejection patterns — high rejection rates may indicate the agent is proposing edits that don't match developer intent. This is a product quality signal.

### 4. Error Landscape

- **429 (Rate Limit)** is the dominant error code — indicates burst usage patterns hitting API limits
- Some models show higher error rates than others, potentially due to availability or quota differences
- Error rates are distributed across teams but peak during certain time windows

**Recommendation**: Implement client-side rate limiting with exponential backoff. Consider requesting higher quotas for heavy-usage practices (Backend, ML Engineering).

### 5. Session Engagement

- Average prompts per session varies significantly across users and practices
- Prompt length distribution shows two clusters: short tactical prompts (~100-200 chars) and longer specification prompts (~400-600 chars)
- Senior engineers (L7+) tend to write longer, more specific prompts

**Recommendation**: The bimodal prompt distribution suggests two distinct usage modes: "quick fix" and "deep work." Product features could optimize for both — quick-action shortcuts for tactical use and structured templates for complex tasks.

---

## Insights for Product Development

| Insight | Impact | Action |
|---|---|---|
| Edit tool rejection is the highest among all tools | Users frequently override agent edit decisions | Improve edit suggestion quality; add preview/diff mode |
| Cache ratio varies 2x across teams | Some teams miss significant cost savings | Build caching dashboards visible to team leads |
| Haiku handles 39% of requests at 3% of cost | Model routing is already partially optimized | Formalize routing rules in agent config |
| P95 latency on Bash tool is significantly higher than others | Long-running commands block user flow | Add timeout warnings and background execution options |
| Rate limit errors concentrated in peak hours | Burst usage exhausts quotas | Deploy request queuing with priority for interactive sessions |

---

## Architecture Approach

### Why This Design?

1. **DuckDB over PostgreSQL**: Zero-config embedded OLAP — perfect for analytical workloads without infrastructure overhead. Columnar storage + vectorized execution handles 500K+ events in seconds.

2. **Star Schema over Flat Tables**: Employee dimension enables slicing by practice/level/location. Fact tables are event-type-specific, avoiding sparse columns.

3. **TRY_CAST over CAST**: Telemetry data is inherently messy (stringified numerics, missing fields). TRY_CAST prevents pipeline failures while explicitly counting and logging rejected rows.

4. **Streamlit over Custom Frontend**: Rapid iteration with built-in data widgets. Plotly integration provides interactive, publication-quality charts without a React build pipeline.

5. **Multi-Persona Design**: Different stakeholders need different views of the same data. A CTO cares about cost governance; a PM cares about adoption; a developer cares about error rates and latency.

---

## Technical Highlights

- **Idempotent Pipeline**: `CREATE OR REPLACE TABLE` + Docker entrypoint = safe to re-run anytime
- **Explicit Validation**: Every TRY_CAST NULL is counted, every orphaned email is reported
- **Custom Agent Skill**: `telemetry_analyzer.py` enables iterative query development during agent-assisted coding
- **26 Automated Tests**: Self-contained fixtures, no dependency on production data
