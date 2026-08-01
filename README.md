# Claude Code Telemetry Analytics Platform

A production-grade analytics platform that processes Claude Code telemetry data (CloudWatch/OTel format) into a DuckDB OLAP database and serves interactive multi-persona dashboards via Streamlit.

## Quick Start

```bash
docker compose up
```

Then open **http://localhost:8501** in your browser.

The platform will:
1. Run the ETL ingestion pipeline (parses `output/telemetry_logs.jsonl` → DuckDB)
2. Launch the Streamlit dashboard with 3 persona views

Re-running `docker compose up` is safe — the pipeline is fully idempotent.

## Architecture

```
output/                          src/ingestion.py              data/telemetry.duckdb
┌──────────────┐    JSON parse   ┌───────────────┐   DuckDB    ┌──────────────────┐
│ telemetry_   │───────────────→ │  ETL Pipeline │────────────→│  Star Schema     │
│ logs.jsonl   │                 │  (TRY_CAST)   │             │  dim_employees   │
├──────────────┤                 └───────────────┘             │  fact_api_reqs   │
│ employees.csv│─────────────────────────────────────────────→ │  fact_tool_usage │
└──────────────┘                                               │  fact_api_errors │
                                                               │  fact_user_prms  │
                                                               └────────┬─────────┘
                                                                        │
                                                               src/analytics.py
                                                                        │
                                                               src/app.py (Streamlit)
                                                                        │
                                                              ┌─────────┴─────────┐
                                                              │  3 Persona Views  │
                                                              │  • CTO / Eng Lead │
                                                              │  • Product Manager│
                                                              │  • Developer      │
                                                              └───────────────────┘
```

### Why DuckDB?

- **Embedded**: Zero infrastructure — no server to run, no network config
- **Columnar OLAP**: Optimized for analytical aggregations (SUM, GROUP BY, percentiles)
- **SQL-native JSON**: `json_extract_string` and `TRY_CAST` handle messy telemetry data safely
- **Fast on single-node**: Processes ~500K events in seconds with vectorized execution

### Why Star Schema?

- **Separation of concerns**: Employee metadata (dimension) is decoupled from event facts
- **Query simplicity**: JOINs on `user_email` enable slicing by practice/level/location
- **Idempotent**: `CREATE OR REPLACE TABLE` makes the pipeline re-runnable without cleanup

### Why TRY_CAST?

All numeric fields in the telemetry JSON arrive as **strings**. Using `CAST` would break the entire pipeline on a single malformed record. `TRY_CAST` converts safely to NULL, and we **count and log** every rejected row explicitly — satisfying the "no silent failures" requirement.

## Data Model

| Table | Description | Key Columns |
|---|---|---|
| `dim_employees` | Employee metadata | email, practice, level, location |
| `fact_api_requests` | API calls to Claude models | model, cost_usd, tokens, duration_ms |
| `fact_tool_usage` | Tool decisions + results | tool_name, decision, is_success, duration_ms |
| `fact_api_errors` | API error events | model, error_message, status_code |
| `fact_user_prompts` | User prompt events | prompt_length |

## Dashboard Personas

### 1. Engineering Lead / CTO
- Total cost, tokens, cache ratio, error rate KPIs
- Cost breakdown by engineering practice and seniority level
- Token efficiency and cache utilization comparison

### 2. Product Manager
- Model adoption breakdown (Haiku/Sonnet/Opus) with pie + bar charts
- Tool usage frequency and rejection rates
- Tool execution success rates and latency distributions

### 3. Developer Insights
- API errors by status code (429, 400, 500) and by model
- Session interaction analysis (prompts per session, prompt length distribution)
- High-latency tool identification with P50/P95/P99 percentiles

## Agent Setup & Tuning

This project was developed using Antigravity IDE with a tuned agent configuration:

### Configuration Files

| File | Purpose |
|---|---|
| `AGENTS.md` | Root agent instructions — project overview and skill documentation |
| `agent/rules/telemetry_rules.md` | Architecture constraints, schema definitions, coding standards |
| `agent/skills/telemetry_analyzer.py` | Custom CLI skill for agent-driven DB queries |

### Custom Skill: `telemetry_analyzer.py`

A Python CLI that lets the agent query `data/telemetry.duckdb` directly during development:

```bash
# List all tables with row counts
python agent/skills/telemetry_analyzer.py --tables

# Show table schema
python agent/skills/telemetry_analyzer.py --schema fact_api_requests

# Run arbitrary SQL
python agent/skills/telemetry_analyzer.py "SELECT model, SUM(cost_usd) FROM fact_api_requests GROUP BY model"
```

**How it was used**: The agent used this skill to:
- Verify ingestion results during pipeline development
- Prototype analytical queries before embedding them in `analytics.py`
- Debug data quality issues (e.g., discovering that all numeric fields are strings in the raw JSON)
- Validate dashboard query outputs match expected row counts

### Rules File: `telemetry_rules.md`

Encodes:
- Complete table schemas with column types
- Mapping of event body types to fact tables
- Constraints: vectorized DuckDB SQL over Python loops, TRY_CAST for all casts, structured logging
- Validation requirements: parse error counts, orphan detection, rejection logging

## Running Tests

```bash
# Install dependencies
pip install -r requirements.txt

# Run all tests
pytest tests/ -v

# Run specific test class
pytest tests/test_ingestion.py::TestTryCastBehavior -v
```

Tests use self-contained in-memory DuckDB fixtures — no dependency on the full dataset.

## Project Structure

```
├── agent/
│   ├── rules/telemetry_rules.md      # Architecture & coding constraints
│   └── skills/telemetry_analyzer.py  # Custom DB query skill
├── data/                             # Generated DuckDB (gitignored)
├── output/
│   ├── telemetry_logs.jsonl          # Source telemetry data
│   └── employees.csv                 # Employee metadata
├── src/
│   ├── ingestion.py                  # ETL pipeline
│   ├── analytics.py                  # SQL query layer
│   └── app.py                        # Streamlit dashboard
├── tests/
│   ├── test_ingestion.py             # Pipeline tests
│   └── test_analytics.py             # Analytics tests
├── AGENTS.md                         # Agent entry point
├── PRESENTATION.md                   # Findings presentation
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Trade-offs & Future Enhancements

### Current Trade-offs
- **In-memory Python parsing**: The JSONL is parsed in Python (not pure DuckDB `read_json_auto`) because the nested `logEvents[].message` contains stringified JSON that requires double-parsing. For a 500MB file this takes ~30s — acceptable for batch but not for streaming.
- **No incremental loads**: Each run rebuilds all tables. Sufficient for the dataset size but would need CDC/watermarking for production.
- **Single-process**: Dashboard and DB share a process. A production system would separate ingestion workers from the serving tier.

### Future Enhancements
- **Incremental ingestion** with DuckDB MERGE/UPSERT for append-only updates
- **Anomaly detection** on cost spikes or error rate changes using statistical models
- **Real-time streaming** via Kafka/Kinesis → DuckDB with micro-batch inserts
- **API layer** (FastAPI) for programmatic metric access
- **Time-series views** with date partitioning for trend analysis
