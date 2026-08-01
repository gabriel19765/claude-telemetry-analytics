"""Tests for analytics query functions.

Verifies aggregation outputs return expected shapes and types
on a small self-contained DuckDB dataset.
"""

import duckdb
import pandas as pd
import pytest


@pytest.fixture
def analytics_db():
    """Create a small in-memory DuckDB with known data for analytics tests."""
    con = duckdb.connect()

    con.execute("""
        CREATE TABLE dim_employees (
            email VARCHAR PRIMARY KEY, full_name VARCHAR,
            practice VARCHAR, level VARCHAR, location VARCHAR
        )
    """)
    con.execute("""
        INSERT INTO dim_employees VALUES
            ('alice@example.com', 'Alice Smith', 'Backend Engineering', 'L5', 'Germany'),
            ('bob@example.com', 'Bob Jones', 'Frontend Engineering', 'L3', 'Poland')
    """)

    con.execute("""
        CREATE TABLE fact_api_requests (
            epoch_ms BIGINT, session_id VARCHAR, user_email VARCHAR,
            model VARCHAR, cost_usd DOUBLE, duration_ms BIGINT,
            input_tokens BIGINT, output_tokens BIGINT,
            cache_read_tokens BIGINT, cache_creation_tokens BIGINT
        )
    """)
    con.execute("""
        INSERT INTO fact_api_requests VALUES
            (1700000000000, 's1', 'alice@example.com', 'claude-sonnet-4-5-20250929', 0.05, 5000, 100, 200, 50, 10),
            (1700000001000, 's1', 'alice@example.com', 'claude-haiku-4-5-20251001', 0.001, 1000, 50, 80, 0, 0),
            (1700000002000, 's2', 'bob@example.com', 'claude-sonnet-4-5-20250929', 0.03, 3000, 80, 150, 30, 5)
    """)

    con.execute("""
        CREATE TABLE fact_tool_usage (
            epoch_ms BIGINT, session_id VARCHAR, user_email VARCHAR,
            tool_name VARCHAR, decision VARCHAR, decision_source VARCHAR,
            is_success BOOLEAN, duration_ms BIGINT
        )
    """)
    con.execute("""
        INSERT INTO fact_tool_usage VALUES
            (1700000000000, 's1', 'alice@example.com', 'Read', 'accept', 'config', NULL, NULL),
            (1700000000100, 's1', 'alice@example.com', 'Read', NULL, NULL, TRUE, 42),
            (1700000001000, 's1', 'alice@example.com', 'Edit', 'reject', 'user_reject', NULL, NULL),
            (1700000002000, 's2', 'bob@example.com', 'Bash', 'accept', 'config', NULL, NULL),
            (1700000002100, 's2', 'bob@example.com', 'Bash', NULL, NULL, FALSE, 500)
    """)

    con.execute("""
        CREATE TABLE fact_api_errors (
            epoch_ms BIGINT, session_id VARCHAR, user_email VARCHAR,
            model VARCHAR, error_message VARCHAR, status_code INTEGER
        )
    """)
    con.execute("""
        INSERT INTO fact_api_errors VALUES
            (1700000003000, 's1', 'alice@example.com', 'claude-sonnet-4-5-20250929', 'rate_limit', 429)
    """)

    con.execute("""
        CREATE TABLE fact_user_prompts (
            epoch_ms BIGINT, session_id VARCHAR, user_email VARCHAR,
            prompt_length BIGINT
        )
    """)
    con.execute("""
        INSERT INTO fact_user_prompts VALUES
            (1700000000000, 's1', 'alice@example.com', 256),
            (1700000001000, 's1', 'alice@example.com', 128),
            (1700000002000, 's2', 'bob@example.com', 512)
    """)

    return con


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestCostAggregations:
    def test_total_cost_sums_correctly(self, analytics_db):
        total = analytics_db.execute(
            "SELECT SUM(cost_usd) FROM fact_api_requests"
        ).fetchone()[0]
        assert abs(total - 0.081) < 1e-6  # 0.05 + 0.001 + 0.03

    def test_cost_by_practice_returns_dataframe(self, analytics_db):
        df = analytics_db.execute("""
            SELECT e.practice, SUM(f.cost_usd) AS total_cost
            FROM fact_api_requests f
            JOIN dim_employees e ON f.user_email = e.email
            GROUP BY e.practice
        """).df()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2  # Backend + Frontend
        assert set(df.columns) == {"practice", "total_cost"}

    def test_cost_per_practice_values(self, analytics_db):
        df = analytics_db.execute("""
            SELECT e.practice, SUM(f.cost_usd) AS total_cost
            FROM fact_api_requests f
            JOIN dim_employees e ON f.user_email = e.email
            GROUP BY e.practice
            ORDER BY e.practice
        """).df()
        backend_cost = df[df["practice"] == "Backend Engineering"]["total_cost"].iloc[0]
        assert abs(backend_cost - 0.051) < 1e-6  # alice: 0.05 + 0.001


class TestPercentages:
    def test_cache_ratio_in_range(self, analytics_db):
        row = analytics_db.execute("""
            SELECT
                SUM(cache_read_tokens) * 100.0 /
                NULLIF(SUM(input_tokens + cache_read_tokens + cache_creation_tokens), 0)
            FROM fact_api_requests
        """).fetchone()[0]
        assert 0 <= row <= 100

    def test_error_rate_in_range(self, analytics_db):
        errors = analytics_db.execute("SELECT COUNT(*) FROM fact_api_errors").fetchone()[0]
        requests = analytics_db.execute("SELECT COUNT(*) FROM fact_api_requests").fetchone()[0]
        rate = errors * 100.0 / (requests + errors)
        assert 0 <= rate <= 100

    def test_tool_reject_rate_in_range(self, analytics_db):
        df = analytics_db.execute("""
            SELECT
                tool_name,
                COUNT(*) FILTER (WHERE decision = 'reject') * 100.0 / NULLIF(COUNT(*), 0) AS reject_pct
            FROM fact_tool_usage
            WHERE decision IS NOT NULL AND decision != ''
            GROUP BY tool_name
        """).df()
        for _, row in df.iterrows():
            assert 0 <= row["reject_pct"] <= 100


class TestOutputShapes:
    def test_model_usage_returns_all_models(self, analytics_db):
        df = analytics_db.execute("""
            SELECT model, COUNT(*) AS cnt
            FROM fact_api_requests
            GROUP BY model
        """).df()
        assert len(df) == 2  # sonnet + haiku

    def test_tool_success_has_expected_columns(self, analytics_db):
        df = analytics_db.execute("""
            SELECT
                tool_name,
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE is_success = TRUE) AS success_count,
                ROUND(COUNT(*) FILTER (WHERE is_success = TRUE) * 100.0 / NULLIF(COUNT(*), 0), 1) AS success_pct
            FROM fact_tool_usage
            WHERE is_success IS NOT NULL
            GROUP BY tool_name
        """).df()
        assert "tool_name" in df.columns
        assert "success_pct" in df.columns

    def test_session_stats_grouping(self, analytics_db):
        df = analytics_db.execute("""
            SELECT session_id, COUNT(*) AS prompt_count
            FROM fact_user_prompts
            GROUP BY session_id
        """).df()
        assert len(df) == 2  # s1 and s2
        s1 = df[df["session_id"] == "s1"]["prompt_count"].iloc[0]
        assert s1 == 2
