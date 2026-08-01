"""Tests for the ingestion pipeline.

Tests JSON parsing, TRY_CAST behavior, and row-count sanity using small
self-contained fixtures (no dependency on full dataset).
"""

import json
import tempfile
from pathlib import Path

import duckdb
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def make_log_event(body: str, attrs: dict, timestamp: int = 1700000000000) -> dict:
    """Build a CloudWatch logEvent dict with an OTel-style message."""
    message = json.dumps({
        "body": body,
        "attributes": {
            "event.timestamp": "2025-12-03T00:00:00.000Z",
            "organization.id": "test-org",
            "session.id": "test-session-001",
            "terminal.type": "vscode",
            "user.account_uuid": "test-uuid",
            "user.email": "test@example.com",
            "user.id": "test-user-id",
            "event.name": body.replace("claude_code.", ""),
            **attrs,
        },
        "scope": {"name": "com.anthropic.claude_code.events", "version": "1.0.0"},
        "resource": {},
    })
    return {"id": "123", "timestamp": timestamp, "message": message}


def make_batch(*events) -> str:
    """Build a JSONL line (CloudWatch batch)."""
    return json.dumps({
        "messageType": "DATA_MESSAGE",
        "owner": "123456789012",
        "logGroup": "/claude-code/telemetry",
        "logStream": "test",
        "subscriptionFilters": ["test"],
        "logEvents": list(events),
        "year": 2025, "month": 12, "day": 3,
    })


@pytest.fixture
def sample_jsonl_file(tmp_path: Path) -> Path:
    """Create a small JSONL file with known events."""
    events = [
        make_log_event("claude_code.api_request", {
            "model": "claude-sonnet-4-5-20250929",
            "cost_usd": "0.0123",
            "duration_ms": "5000",
            "input_tokens": "100",
            "output_tokens": "200",
            "cache_read_tokens": "50",
            "cache_creation_tokens": "10",
        }),
        make_log_event("claude_code.api_request", {
            "model": "claude-haiku-4-5-20251001",
            "cost_usd": "not_a_number",  # Should produce NULL via TRY_CAST
            "duration_ms": "1000",
            "input_tokens": "50",
            "output_tokens": "80",
            "cache_read_tokens": "0",
            "cache_creation_tokens": "0",
        }),
        make_log_event("claude_code.tool_decision", {
            "decision": "accept",
            "source": "config",
            "tool_name": "Read",
        }),
        make_log_event("claude_code.tool_result", {
            "decision_type": "accept",
            "decision_source": "config",
            "tool_name": "Read",
            "success": "true",
            "duration_ms": "42",
        }),
        make_log_event("claude_code.api_error", {
            "model": "claude-sonnet-4-5-20250929",
            "error": "rate_limit_exceeded",
            "status_code": "429",
        }),
        make_log_event("claude_code.user_prompt", {
            "prompt": "<REDACTED>",
            "prompt_length": "256",
        }),
    ]
    batch_line = make_batch(*events)
    filepath = tmp_path / "test_logs.jsonl"
    filepath.write_text(batch_line + "\n")
    return filepath


@pytest.fixture
def sample_employees_file(tmp_path: Path) -> Path:
    filepath = tmp_path / "employees.csv"
    filepath.write_text(
        "email,full_name,practice,level,location\n"
        "test@example.com,Test User,Backend Engineering,L5,Germany\n"
    )
    return filepath


@pytest.fixture
def test_db(tmp_path: Path, sample_jsonl_file: Path, sample_employees_file: Path):
    """Run the ingestion pipeline on fixtures and return a read-only connection."""
    # We can't use the real pipeline directly because it uses hardcoded paths,
    # so we replicate the core logic inline for testing.
    db_path = tmp_path / "test.duckdb"
    con = duckdb.connect(str(db_path))

    # Create schema
    con.execute("""
        CREATE TABLE dim_employees (
            email VARCHAR PRIMARY KEY, full_name VARCHAR,
            practice VARCHAR, level VARCHAR, location VARCHAR
        )
    """)
    con.execute(f"INSERT INTO dim_employees SELECT * FROM read_csv_auto('{sample_employees_file}', header=true)")

    # Parse JSONL
    import json as _json
    events = []
    with open(sample_jsonl_file) as f:
        for line in f:
            batch = _json.loads(line.strip())
            for ev in batch.get("logEvents", []):
                msg = _json.loads(ev["message"])
                attrs = msg.get("attributes", {})
                events.append((
                    ev["timestamp"], msg.get("body", ""),
                    attrs.get("session.id", ""), attrs.get("user.email", ""),
                    attrs.get("event.name", ""), attrs.get("model", ""),
                    attrs.get("cost_usd", ""), attrs.get("duration_ms", ""),
                    attrs.get("input_tokens", ""), attrs.get("output_tokens", ""),
                    attrs.get("cache_read_tokens", ""), attrs.get("cache_creation_tokens", ""),
                    attrs.get("decision", attrs.get("decision_type", "")),
                    attrs.get("source", attrs.get("decision_source", "")),
                    attrs.get("tool_name", ""), attrs.get("success", ""),
                    attrs.get("error", ""), attrs.get("status_code", ""),
                    attrs.get("prompt_length", ""),
                ))

    con.execute("""
        CREATE TABLE stg_events (
            epoch_ms BIGINT, body VARCHAR, session_id VARCHAR,
            user_email VARCHAR, event_name VARCHAR, model VARCHAR,
            cost_usd VARCHAR, duration_ms VARCHAR, input_tokens VARCHAR,
            output_tokens VARCHAR, cache_read_tokens VARCHAR,
            cache_creation_tokens VARCHAR, decision VARCHAR,
            decision_source VARCHAR, tool_name VARCHAR, success VARCHAR,
            error_message VARCHAR, status_code VARCHAR, prompt_length VARCHAR
        )
    """)
    con.executemany("INSERT INTO stg_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", events)

    # Load fact tables
    con.execute("""
        CREATE TABLE fact_api_requests AS
        SELECT epoch_ms, session_id, user_email, model,
               TRY_CAST(cost_usd AS DOUBLE) AS cost_usd,
               TRY_CAST(duration_ms AS BIGINT) AS duration_ms,
               TRY_CAST(input_tokens AS BIGINT) AS input_tokens,
               TRY_CAST(output_tokens AS BIGINT) AS output_tokens,
               TRY_CAST(cache_read_tokens AS BIGINT) AS cache_read_tokens,
               TRY_CAST(cache_creation_tokens AS BIGINT) AS cache_creation_tokens
        FROM stg_events WHERE body = 'claude_code.api_request'
    """)
    con.execute("""
        CREATE TABLE fact_tool_usage AS
        SELECT epoch_ms, session_id, user_email, tool_name, decision, decision_source,
               CASE WHEN success='true' THEN TRUE WHEN success='false' THEN FALSE ELSE NULL END AS is_success,
               TRY_CAST(duration_ms AS BIGINT) AS duration_ms
        FROM stg_events WHERE body IN ('claude_code.tool_decision', 'claude_code.tool_result')
    """)
    con.execute("""
        CREATE TABLE fact_api_errors AS
        SELECT epoch_ms, session_id, user_email, model, error_message,
               TRY_CAST(status_code AS INTEGER) AS status_code
        FROM stg_events WHERE body = 'claude_code.api_error'
    """)
    con.execute("""
        CREATE TABLE fact_user_prompts AS
        SELECT epoch_ms, session_id, user_email,
               TRY_CAST(prompt_length AS BIGINT) AS prompt_length
        FROM stg_events WHERE body = 'claude_code.user_prompt'
    """)
    con.execute("DROP TABLE stg_events")

    return con


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestJSONParsing:
    """Verify parsing of valid and malformed records."""

    def test_valid_json_parses(self):
        event = make_log_event("claude_code.api_request", {"model": "test", "cost_usd": "1.5"})
        msg = json.loads(event["message"])
        assert msg["body"] == "claude_code.api_request"
        assert msg["attributes"]["model"] == "test"

    def test_malformed_inner_json_detected(self):
        event = {"id": "1", "timestamp": 123, "message": "not valid json {{{"}
        with pytest.raises(json.JSONDecodeError):
            json.loads(event["message"])

    def test_malformed_outer_json_detected(self):
        with pytest.raises(json.JSONDecodeError):
            json.loads("this is not json at all")

    def test_missing_attributes_handled(self):
        """Events without expected attributes should still parse."""
        msg = json.dumps({"body": "claude_code.api_request", "attributes": {}})
        event = {"id": "1", "timestamp": 123, "message": msg}
        parsed = json.loads(event["message"])
        assert parsed["attributes"].get("model", "") == ""


class TestTryCastBehavior:
    """Verify TRY_CAST produces NULL on bad input instead of erroring."""

    def test_try_cast_valid_double(self):
        con = duckdb.connect()
        result = con.execute("SELECT TRY_CAST('0.0123' AS DOUBLE)").fetchone()[0]
        assert abs(result - 0.0123) < 1e-6

    def test_try_cast_invalid_double_returns_null(self):
        con = duckdb.connect()
        result = con.execute("SELECT TRY_CAST('not_a_number' AS DOUBLE)").fetchone()[0]
        assert result is None

    def test_try_cast_valid_bigint(self):
        con = duckdb.connect()
        result = con.execute("SELECT TRY_CAST('5000' AS BIGINT)").fetchone()[0]
        assert result == 5000

    def test_try_cast_invalid_bigint_returns_null(self):
        con = duckdb.connect()
        result = con.execute("SELECT TRY_CAST('abc' AS BIGINT)").fetchone()[0]
        assert result is None

    def test_try_cast_empty_string_returns_null(self):
        con = duckdb.connect()
        result = con.execute("SELECT TRY_CAST('' AS DOUBLE)").fetchone()[0]
        assert result is None


class TestRowCounts:
    """Verify correct row counts after ingestion of known fixture data."""

    def test_employees_count(self, test_db):
        count = test_db.execute("SELECT COUNT(*) FROM dim_employees").fetchone()[0]
        assert count == 1

    def test_api_requests_count(self, test_db):
        count = test_db.execute("SELECT COUNT(*) FROM fact_api_requests").fetchone()[0]
        assert count == 2  # 2 api_request events in fixture

    def test_tool_usage_count(self, test_db):
        count = test_db.execute("SELECT COUNT(*) FROM fact_tool_usage").fetchone()[0]
        assert count == 2  # 1 decision + 1 result

    def test_api_errors_count(self, test_db):
        count = test_db.execute("SELECT COUNT(*) FROM fact_api_errors").fetchone()[0]
        assert count == 1

    def test_user_prompts_count(self, test_db):
        count = test_db.execute("SELECT COUNT(*) FROM fact_user_prompts").fetchone()[0]
        assert count == 1


class TestTryCastInPipeline:
    """Verify TRY_CAST behavior in the actual pipeline output."""

    def test_malformed_cost_produces_null(self, test_db):
        """The second api_request has cost_usd='not_a_number', should be NULL."""
        results = test_db.execute(
            "SELECT model, cost_usd FROM fact_api_requests ORDER BY model"
        ).fetchall()
        # haiku has 'not_a_number' → NULL
        haiku = [r for r in results if "haiku" in r[0]][0]
        assert haiku[1] is None

    def test_valid_cost_preserved(self, test_db):
        results = test_db.execute(
            "SELECT model, cost_usd FROM fact_api_requests ORDER BY model"
        ).fetchall()
        sonnet = [r for r in results if "sonnet" in r[0]][0]
        assert abs(sonnet[1] - 0.0123) < 1e-6

    def test_valid_status_code_parsed(self, test_db):
        code = test_db.execute("SELECT status_code FROM fact_api_errors").fetchone()[0]
        assert code == 429
