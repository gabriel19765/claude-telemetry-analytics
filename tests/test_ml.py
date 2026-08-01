"""Unit tests for ML anomaly detection functions in src/ml.py."""

import duckdb
import pytest
import pandas as pd

from src.ml import detect_cost_anomalies, detect_latency_anomalies, get_anomaly_summary


@pytest.fixture
def mock_db():
    con = duckdb.connect(":memory:")
    con.execute("""
        CREATE TABLE fact_api_requests (
            epoch_ms BIGINT, session_id VARCHAR, user_email VARCHAR, model VARCHAR,
            cost_usd DOUBLE, duration_ms BIGINT, input_tokens BIGINT, output_tokens BIGINT,
            cache_read_tokens BIGINT, cache_creation_tokens BIGINT
        );
    """)
    # Insert normal costs ~ 0.05 and one anomaly of 15.0
    for i in range(50):
        con.execute(f"INSERT INTO fact_api_requests VALUES (1000, 's1', 'u1@ex.com', 'm1', 0.05, 100, 10, 10, 0, 0)")
    con.execute("INSERT INTO fact_api_requests VALUES (1001, 's1', 'u1@ex.com', 'm1', 15.0, 100, 10, 10, 0, 0)")

    con.execute("""
        CREATE TABLE fact_tool_usage (
            epoch_ms BIGINT, session_id VARCHAR, user_email VARCHAR, tool_name VARCHAR,
            decision VARCHAR, decision_source VARCHAR, is_success BOOLEAN, duration_ms BIGINT
        );
    """)
    for i in range(50):
        con.execute("INSERT INTO fact_tool_usage VALUES (1000, 's1', 'u1@ex.com', 'Bash', 'accept', 'config', true, 50)")
    con.execute("INSERT INTO fact_tool_usage VALUES (1001, 's1', 'u1@ex.com', 'Bash', 'accept', 'config', true, 5000)")

    yield con
    con.close()


def test_detect_cost_anomalies_finds_outlier(mock_db):
    df = detect_cost_anomalies(mock_db, z_threshold=2.0)
    assert not df.empty
    assert df.iloc[0]["cost_usd"] == 15.0


def test_detect_latency_anomalies_finds_outlier(mock_db):
    df = detect_latency_anomalies(mock_db, iqr_multiplier=1.5)
    assert not df.empty
    assert df.iloc[0]["duration_ms"] == 5000


def test_get_anomaly_summary(mock_db):
    summary = get_anomaly_summary(mock_db)
    assert summary["cost_anomaly_count"] >= 1
    assert summary["total_anomalous_cost_usd"] >= 15.0
