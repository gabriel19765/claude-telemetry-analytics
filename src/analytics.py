"""Analytical SQL queries and aggregation functions over DuckDB.

All functions accept a DuckDB connection and return pandas DataFrames
for direct consumption by Streamlit/Plotly.
"""

from pathlib import Path

import duckdb
import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "telemetry.duckdb"


def get_connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH), read_only=True)


# ===================================================================
# Persona 1: Engineering Lead / CTO — Costs, Efficiency & Governance
# ===================================================================

def total_cost(con: duckdb.DuckDBPyConnection) -> float:
    return con.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM fact_api_requests").fetchone()[0]


def total_tokens(con: duckdb.DuckDBPyConnection) -> int:
    return con.execute(
        "SELECT COALESCE(SUM(input_tokens + output_tokens), 0) FROM fact_api_requests"
    ).fetchone()[0]


def cache_read_ratio(con: duckdb.DuckDBPyConnection) -> float:
    """Cache read tokens as % of all input tokens (input + cache_read + cache_creation)."""
    row = con.execute("""
        SELECT
            COALESCE(SUM(cache_read_tokens), 0) AS cache_reads,
            COALESCE(SUM(input_tokens + cache_read_tokens + cache_creation_tokens), 0) AS total_input
        FROM fact_api_requests
    """).fetchone()
    if row[1] == 0:
        return 0.0
    return (row[0] / row[1]) * 100


def api_error_rate(con: duckdb.DuckDBPyConnection) -> float:
    """API errors as % of total API requests + errors."""
    errors = con.execute("SELECT COUNT(*) FROM fact_api_errors").fetchone()[0]
    requests = con.execute("SELECT COUNT(*) FROM fact_api_requests").fetchone()[0]
    total = requests + errors
    if total == 0:
        return 0.0
    return (errors / total) * 100


def cost_by_practice(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute("""
        SELECT
            e.practice,
            SUM(f.cost_usd) AS total_cost,
            SUM(f.input_tokens + f.output_tokens) AS total_tokens,
            COUNT(*) AS request_count
        FROM fact_api_requests f
        JOIN dim_employees e ON f.user_email = e.email
        GROUP BY e.practice
        ORDER BY total_cost DESC
    """).df()


def cost_by_level(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute("""
        SELECT
            e.level,
            SUM(f.cost_usd) AS total_cost,
            SUM(f.input_tokens + f.output_tokens) AS total_tokens,
            COUNT(*) AS request_count
        FROM fact_api_requests f
        JOIN dim_employees e ON f.user_email = e.email
        GROUP BY e.level
        ORDER BY CAST(REPLACE(e.level, 'L', '') AS INTEGER)
    """).df()


def token_efficiency_by_practice(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Avg cost per 1K tokens and cache utilization by practice."""
    return con.execute("""
        SELECT
            e.practice,
            ROUND(AVG(f.cost_usd) * 1000, 4) AS avg_cost_per_request_x1000,
            ROUND(
                SUM(f.cache_read_tokens) * 100.0 /
                NULLIF(SUM(f.input_tokens + f.cache_read_tokens + f.cache_creation_tokens), 0),
                1
            ) AS cache_hit_pct,
            ROUND(AVG(f.duration_ms), 0) AS avg_duration_ms
        FROM fact_api_requests f
        JOIN dim_employees e ON f.user_email = e.email
        GROUP BY e.practice
        ORDER BY e.practice
    """).df()


# ===================================================================
# Persona 2: Product Manager — Adoption & Tool Analytics
# ===================================================================

def model_usage_breakdown(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute("""
        SELECT
            model,
            COUNT(*) AS request_count,
            SUM(cost_usd) AS total_cost,
            SUM(input_tokens + output_tokens) AS total_tokens
        FROM fact_api_requests
        GROUP BY model
        ORDER BY request_count DESC
    """).df()


def tool_usage_frequency(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute("""
        SELECT
            tool_name,
            COUNT(*) AS usage_count,
            COUNT(*) FILTER (WHERE decision = 'reject') AS reject_count,
            ROUND(
                COUNT(*) FILTER (WHERE decision = 'reject') * 100.0 / NULLIF(COUNT(*), 0),
                1
            ) AS reject_rate_pct
        FROM fact_tool_usage
        WHERE decision IS NOT NULL AND decision != ''
        GROUP BY tool_name
        ORDER BY usage_count DESC
    """).df()


def tool_success_rates(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute("""
        SELECT
            tool_name,
            COUNT(*) AS total_results,
            COUNT(*) FILTER (WHERE is_success = TRUE) AS success_count,
            ROUND(
                COUNT(*) FILTER (WHERE is_success = TRUE) * 100.0 / NULLIF(COUNT(*), 0),
                1
            ) AS success_rate_pct,
            ROUND(AVG(duration_ms), 0) AS avg_duration_ms,
            ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms), 0) AS p95_duration_ms
        FROM fact_tool_usage
        WHERE is_success IS NOT NULL
        GROUP BY tool_name
        ORDER BY total_results DESC
    """).df()


def tool_latency_distribution(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute("""
        SELECT tool_name, duration_ms
        FROM fact_tool_usage
        WHERE duration_ms IS NOT NULL AND duration_ms > 0
    """).df()


# ===================================================================
# Persona 3: Developer Insights — Performance & Operational Health
# ===================================================================

def common_api_errors(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute("""
        SELECT
            status_code,
            error_message,
            COUNT(*) AS error_count,
            COUNT(DISTINCT user_email) AS affected_users
        FROM fact_api_errors
        GROUP BY status_code, error_message
        ORDER BY error_count DESC
    """).df()


def error_rate_by_model(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute("""
        WITH requests AS (
            SELECT model, COUNT(*) AS cnt FROM fact_api_requests GROUP BY model
        ),
        errors AS (
            SELECT model, COUNT(*) AS cnt FROM fact_api_errors GROUP BY model
        )
        SELECT
            COALESCE(r.model, e.model) AS model,
            COALESCE(r.cnt, 0) AS request_count,
            COALESCE(e.cnt, 0) AS error_count,
            ROUND(COALESCE(e.cnt, 0) * 100.0 / NULLIF(COALESCE(r.cnt, 0) + COALESCE(e.cnt, 0), 0), 1) AS error_rate_pct
        FROM requests r
        FULL OUTER JOIN errors e ON r.model = e.model
        ORDER BY error_rate_pct DESC
    """).df()


def session_interaction_stats(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Average prompts per session and prompt length distribution."""
    return con.execute("""
        SELECT
            session_id,
            user_email,
            COUNT(*) AS prompt_count,
            ROUND(AVG(prompt_length), 0) AS avg_prompt_length,
            MIN(epoch_ms) AS session_start,
            MAX(epoch_ms) AS session_end
        FROM fact_user_prompts
        GROUP BY session_id, user_email
        ORDER BY prompt_count DESC
    """).df()


def prompt_length_distribution(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute("""
        SELECT prompt_length
        FROM fact_user_prompts
        WHERE prompt_length IS NOT NULL AND prompt_length > 0
    """).df()


def high_latency_tools(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute("""
        SELECT
            tool_name,
            COUNT(*) AS call_count,
            ROUND(AVG(duration_ms), 0) AS avg_ms,
            ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY duration_ms), 0) AS p50_ms,
            ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms), 0) AS p95_ms,
            ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY duration_ms), 0) AS p99_ms,
            MAX(duration_ms) AS max_ms
        FROM fact_tool_usage
        WHERE duration_ms IS NOT NULL AND duration_ms > 0
        GROUP BY tool_name
        ORDER BY p95_ms DESC
    """).df()


def api_request_latency_by_model(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute("""
        SELECT
            model,
            COUNT(*) AS request_count,
            ROUND(AVG(duration_ms), 0) AS avg_ms,
            ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY duration_ms), 0) AS p50_ms,
            ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms), 0) AS p95_ms,
            MAX(duration_ms) AS max_ms
        FROM fact_api_requests
        WHERE duration_ms IS NOT NULL
        GROUP BY model
        ORDER BY avg_ms DESC
    """).df()
