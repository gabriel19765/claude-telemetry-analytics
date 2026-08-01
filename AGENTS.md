# AGENTS.md — Claude Code Telemetry Analytics Platform

## Project Overview
This is an analytics platform that processes Claude Code telemetry logs (CloudWatch/OTel format) into a DuckDB OLAP database, then serves interactive Streamlit dashboards for multiple personas.

## Architecture
- **Ingestion**: `src/ingestion.py` — parses JSONL → DuckDB star schema
- **Analytics**: `src/analytics.py` — SQL query layer over DuckDB
- **Dashboard**: `src/app.py` — Streamlit multi-persona UI
- **Database**: `data/telemetry.duckdb` (generated at runtime)

## Agent Rules
See [agent/rules/telemetry_rules.md](agent/rules/telemetry_rules.md) for architecture constraints, coding style, and data handling requirements.

## Custom Skill: Telemetry Analyzer
The agent has a custom Python skill at `agent/skills/telemetry_analyzer.py` for querying the DuckDB database directly.

### Usage
```bash
python agent/skills/telemetry_analyzer.py "SELECT COUNT(*) FROM fact_api_requests"
python agent/skills/telemetry_analyzer.py "SELECT model, SUM(cost_usd) FROM fact_api_requests GROUP BY model"
python agent/skills/telemetry_analyzer.py --tables  # List all tables
python agent/skills/telemetry_analyzer.py --schema fact_api_requests  # Show table schema
```

This skill enables the agent to:
1. Inspect table schemas and row counts
2. Run ad-hoc analytical queries during development
3. Validate ingestion results
4. Prototype dashboard queries before embedding them in code

## Running
```bash
docker compose up
```

## Testing
```bash
pytest tests/ -v
```
