"""Machine Learning & Anomaly Detection module for telemetry data.

Implements statistical anomaly detection (Z-score & IQR methods) over
DuckDB data for identifying high-cost API requests and duration outliers.
"""

from pathlib import Path
import duckdb
import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "telemetry.duckdb"


def detect_cost_anomalies(con: duckdb.DuckDBPyConnection, z_threshold: float = 3.0) -> pd.DataFrame:
    """Detect cost anomalies using Z-score thresholding (> N std deviations)."""
    return con.execute(f"""
        WITH stats AS (
            SELECT
                AVG(cost_usd) AS mean_cost,
                STDDEV(cost_usd) AS std_cost
            FROM fact_api_requests
            WHERE cost_usd IS NOT NULL AND cost_usd > 0
        )
        SELECT
            f.epoch_ms,
            strftime(to_timestamp(f.epoch_ms / 1000), '%Y-%m-%d %H:%M:%S') AS timestamp,
            f.user_email,
            f.model,
            ROUND(f.cost_usd, 4) AS cost_usd,
            f.duration_ms,
            ROUND(f.duration_ms / 1000.0, 2) AS duration_sec,
            ROUND((f.cost_usd - s.mean_cost) / NULLIF(s.std_cost, 0), 2) AS z_score,
            f.session_id
        FROM fact_api_requests f, stats s
        WHERE f.cost_usd > 0
          AND (f.cost_usd - s.mean_cost) / NULLIF(s.std_cost, 0) >= {z_threshold}
        ORDER BY f.cost_usd DESC
    """).df()


def detect_latency_anomalies(con: duckdb.DuckDBPyConnection, iqr_multiplier: float = 1.5) -> pd.DataFrame:
    """Detect tool latency outliers using Interquartile Range (IQR) method."""
    return con.execute(f"""
        WITH bounds AS (
            SELECT
                tool_name,
                PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY duration_ms) AS q1,
                PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY duration_ms) AS q3
            FROM fact_tool_usage
            WHERE duration_ms IS NOT NULL AND duration_ms > 0
            GROUP BY tool_name
        )
        SELECT
            f.epoch_ms,
            strftime(to_timestamp(f.epoch_ms / 1000), '%Y-%m-%d %H:%M:%S') AS timestamp,
            f.user_email,
            f.tool_name,
            f.duration_ms,
            ROUND(f.duration_ms / 1000.0, 2) AS duration_sec,
            ROUND((b.q3 + ({iqr_multiplier} * (b.q3 - b.q1))) / 1000.0, 2) AS threshold_sec,
            f.session_id
        FROM fact_tool_usage f
        JOIN bounds b ON f.tool_name = b.tool_name
        WHERE f.duration_ms > (b.q3 + ({iqr_multiplier} * (b.q3 - b.q1)))
        ORDER BY f.duration_ms DESC
        LIMIT 100
    """).df()


def get_anomaly_summary(con: duckdb.DuckDBPyConnection) -> dict:
    """Return summary statistics on detected anomalies."""
    cost_anomalies = detect_cost_anomalies(con)
    latency_anomalies = detect_latency_anomalies(con)
    return {
        "cost_anomaly_count": len(cost_anomalies),
        "total_anomalous_cost_usd": round(cost_anomalies["cost_usd"].sum() if not cost_anomalies.empty else 0.0, 2),
        "latency_anomaly_count": len(latency_anomalies),
        "max_latency_sec": round(latency_anomalies["duration_sec"].max() if not latency_anomalies.empty else 0.0, 1),
    }
