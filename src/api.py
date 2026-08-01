"""FastAPI REST API endpoints for programmatic access to telemetry metrics and ML anomalies.

Provides endpoints for health checks, aggregated metrics, cost breakdowns, tool statistics,
and anomaly detection results.
"""

from pathlib import Path
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException
import duckdb

from src import analytics, ml

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "telemetry.duckdb"

app = FastAPI(
    title="Claude Code Telemetry Analytics API",
    description="Programmatic access to Claude Code usage metrics, aggregations, and ML anomaly detection.",
    version="1.0.0",
)


def get_con() -> duckdb.DuckDBPyConnection:
    if not DB_PATH.exists():
        raise HTTPException(status_code=503, detail="Database telemetry.duckdb not found. Run ingestion first.")
    return duckdb.connect(str(DB_PATH), read_only=True)


@app.get("/health", summary="Service Health Check")
def health_check() -> Dict[str, str]:
    if DB_PATH.exists():
        return {"status": "ok", "database": "connected"}
    return {"status": "degraded", "database": "missing"}


@app.get("/api/v1/metrics/kpis", summary="Top-Level KPIs")
def get_kpis() -> Dict[str, Any]:
    con = get_con()
    try:
        return {
            "total_cost_usd": round(analytics.total_cost(con), 2),
            "total_tokens": analytics.total_tokens(con),
            "cache_read_ratio_pct": round(analytics.cache_read_ratio(con), 1),
            "api_error_rate_pct": round(analytics.api_error_rate(con), 1),
        }
    finally:
        con.close()


@app.get("/api/v1/metrics/costs/by-practice", summary="Cost Breakdown by Engineering Practice")
def cost_by_practice() -> List[Dict[str, Any]]:
    con = get_con()
    try:
        df = analytics.cost_by_practice(con)
        return df.to_dict(orient="records")
    finally:
        con.close()


@app.get("/api/v1/metrics/models", summary="Model Usage Breakdown")
def model_usage() -> List[Dict[str, Any]]:
    con = get_con()
    try:
        df = analytics.model_usage_breakdown(con)
        return df.to_dict(orient="records")
    finally:
        con.close()


@app.get("/api/v1/metrics/tools", summary="Tool Usage Frequency & Rejection Rates")
def tool_usage() -> List[Dict[str, Any]]:
    con = get_con()
    try:
        df = analytics.tool_usage_frequency(con)
        return df.to_dict(orient="records")
    finally:
        con.close()


@app.get("/api/v1/anomalies/summary", summary="ML Anomaly Detection Summary")
def anomaly_summary() -> Dict[str, Any]:
    con = get_con()
    try:
        return ml.get_anomaly_summary(con)
    finally:
        con.close()


@app.get("/api/v1/anomalies/cost", summary="Detected Cost Anomalies (Z-Score > 3)")
def cost_anomalies(z_threshold: float = 3.0) -> List[Dict[str, Any]]:
    con = get_con()
    try:
        df = ml.detect_cost_anomalies(con, z_threshold=z_threshold)
        return df.to_dict(orient="records")
    finally:
        con.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
