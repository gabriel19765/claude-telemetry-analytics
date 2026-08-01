"""ETL pipeline: JSONL telemetry logs → DuckDB star schema.

Reads CloudWatch log batches from output/telemetry_logs.jsonl, unnests logEvents,
parses stringified JSON messages, and loads into strongly-typed fact tables with
safe TRY_CAST conversions. Fully idempotent (CREATE OR REPLACE).
"""

import json
import sys
import time
from pathlib import Path

import duckdb

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "telemetry.duckdb"
LOGS_PATH = PROJECT_ROOT / "output" / "telemetry_logs.jsonl"
EMPLOYEES_PATH = PROJECT_ROOT / "output" / "employees.csv"


def log(tag: str, msg: str) -> None:
    print(f"[{tag}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# 1. Connection & Schema
# ---------------------------------------------------------------------------
def get_connection() -> duckdb.DuckDBPyConnection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DB_PATH))


def create_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Create all tables using CREATE OR REPLACE for idempotency."""
    con.execute("""
        CREATE OR REPLACE TABLE dim_employees (
            email       VARCHAR PRIMARY KEY,
            full_name   VARCHAR,
            practice    VARCHAR,
            level       VARCHAR,
            location    VARCHAR
        )
    """)
    con.execute("""
        CREATE OR REPLACE TABLE fact_api_requests (
            epoch_ms              BIGINT,
            session_id            VARCHAR,
            user_email            VARCHAR,
            model                 VARCHAR,
            cost_usd              DOUBLE,
            duration_ms           BIGINT,
            input_tokens          BIGINT,
            output_tokens         BIGINT,
            cache_read_tokens     BIGINT,
            cache_creation_tokens BIGINT
        )
    """)
    con.execute("""
        CREATE OR REPLACE TABLE fact_tool_usage (
            epoch_ms         BIGINT,
            session_id       VARCHAR,
            user_email       VARCHAR,
            tool_name        VARCHAR,
            decision         VARCHAR,
            decision_source  VARCHAR,
            is_success       BOOLEAN,
            duration_ms      BIGINT
        )
    """)
    con.execute("""
        CREATE OR REPLACE TABLE fact_api_errors (
            epoch_ms       BIGINT,
            session_id     VARCHAR,
            user_email     VARCHAR,
            model          VARCHAR,
            error_message  VARCHAR,
            status_code    INTEGER
        )
    """)
    con.execute("""
        CREATE OR REPLACE TABLE fact_user_prompts (
            epoch_ms       BIGINT,
            session_id     VARCHAR,
            user_email     VARCHAR,
            prompt_length  BIGINT
        )
    """)
    log("SCHEMA", "All tables created (CREATE OR REPLACE)")


# ---------------------------------------------------------------------------
# 2. Load dim_employees
# ---------------------------------------------------------------------------
def load_employees(con: duckdb.DuckDBPyConnection) -> None:
    if not EMPLOYEES_PATH.exists():
        log("ERROR", f"Employees file not found: {EMPLOYEES_PATH}")
        sys.exit(1)

    # Validate expected columns
    with open(EMPLOYEES_PATH) as f:
        header = f.readline().strip().replace("\r", "")
    expected = {"email", "full_name", "practice", "level", "location"}
    actual = set(header.split(","))
    missing = expected - actual
    if missing:
        log("ERROR", f"Missing columns in employees.csv: {missing}")
        sys.exit(1)

    con.execute(f"""
        INSERT INTO dim_employees
        SELECT * FROM read_csv_auto('{EMPLOYEES_PATH}', header=true)
    """)
    count = con.execute("SELECT COUNT(*) FROM dim_employees").fetchone()[0]
    log("INGEST", f"dim_employees: {count:,} rows loaded")


# ---------------------------------------------------------------------------
# 3. Parse JSONL → staging table
# ---------------------------------------------------------------------------
def load_raw_events(con: duckdb.DuckDBPyConnection) -> int:
    """Parse JSONL, unnest logEvents, extract message JSON into a staging table.

    Returns total number of raw events processed.
    """
    if not LOGS_PATH.exists():
        log("ERROR", f"Telemetry file not found: {LOGS_PATH}")
        sys.exit(1)

    log("INGEST", f"Reading {LOGS_PATH.name} ...")
    t0 = time.time()

    # Read all log events — each line is a CloudWatch batch with logEvents[]
    # We parse the outer JSON, unnest logEvents, then parse the inner message JSON
    parse_errors = 0
    events: list[dict] = []

    with open(LOGS_PATH) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                batch = json.loads(line)
            except json.JSONDecodeError as e:
                parse_errors += 1
                if parse_errors <= 5:
                    log("WARN", f"Line {line_num}: failed to parse outer JSON: {e}")
                continue

            for event in batch.get("logEvents", []):
                msg_str = event.get("message", "")
                try:
                    msg = json.loads(msg_str)
                except json.JSONDecodeError:
                    parse_errors += 1
                    if parse_errors <= 10:
                        log("WARN", f"Line {line_num}: failed to parse inner message JSON")
                    continue

                attrs = msg.get("attributes", {})
                events.append({
                    "epoch_ms": event.get("timestamp"),
                    "body": msg.get("body", ""),
                    "session_id": attrs.get("session.id", ""),
                    "user_email": attrs.get("user.email", ""),
                    "event_name": attrs.get("event.name", ""),
                    # api_request fields
                    "model": attrs.get("model", ""),
                    "cost_usd": attrs.get("cost_usd", ""),
                    "duration_ms": attrs.get("duration_ms", ""),
                    "input_tokens": attrs.get("input_tokens", ""),
                    "output_tokens": attrs.get("output_tokens", ""),
                    "cache_read_tokens": attrs.get("cache_read_tokens", ""),
                    "cache_creation_tokens": attrs.get("cache_creation_tokens", ""),
                    # tool_decision fields
                    "decision": attrs.get("decision", attrs.get("decision_type", "")),
                    "decision_source": attrs.get("source", attrs.get("decision_source", "")),
                    "tool_name": attrs.get("tool_name", ""),
                    # tool_result fields
                    "success": attrs.get("success", ""),
                    # api_error fields
                    "error_message": attrs.get("error", ""),
                    "status_code": attrs.get("status_code", ""),
                    # user_prompt fields
                    "prompt_length": attrs.get("prompt_length", ""),
                })

    elapsed = time.time() - t0
    log("INGEST", f"Parsed {len(events):,} events in {elapsed:.1f}s ({parse_errors:,} parse errors)")

    # Load into a staging table via DuckDB
    con.execute("CREATE OR REPLACE TABLE stg_events AS SELECT * FROM stg_events LIMIT 0") if False else None
    con.execute("""
        CREATE OR REPLACE TABLE stg_events (
            epoch_ms              BIGINT,
            body                  VARCHAR,
            session_id            VARCHAR,
            user_email            VARCHAR,
            event_name            VARCHAR,
            model                 VARCHAR,
            cost_usd              VARCHAR,
            duration_ms           VARCHAR,
            input_tokens          VARCHAR,
            output_tokens         VARCHAR,
            cache_read_tokens     VARCHAR,
            cache_creation_tokens VARCHAR,
            decision              VARCHAR,
            decision_source       VARCHAR,
            tool_name             VARCHAR,
            success               VARCHAR,
            error_message         VARCHAR,
            status_code           VARCHAR,
            prompt_length         VARCHAR
        )
    """)

    # Write events to temp CSV and load via DuckDB's native reader (avoids pandas dependency)
    import csv
    import tempfile

    staging_csv = Path(tempfile.mktemp(suffix=".csv", dir=str(DB_PATH.parent)))
    columns = [
        "epoch_ms", "body", "session_id", "user_email", "event_name", "model",
        "cost_usd", "duration_ms", "input_tokens", "output_tokens",
        "cache_read_tokens", "cache_creation_tokens", "decision",
        "decision_source", "tool_name", "success", "error_message",
        "status_code", "prompt_length",
    ]
    try:
        with open(staging_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            writer.writerows(events)

        con.execute(f"""
            INSERT INTO stg_events
            SELECT * FROM read_csv_auto('{staging_csv}', header=true, all_varchar=true,
                                         columns={{'epoch_ms': 'BIGINT',
                                                   'body': 'VARCHAR', 'session_id': 'VARCHAR',
                                                   'user_email': 'VARCHAR', 'event_name': 'VARCHAR',
                                                   'model': 'VARCHAR', 'cost_usd': 'VARCHAR',
                                                   'duration_ms': 'VARCHAR', 'input_tokens': 'VARCHAR',
                                                   'output_tokens': 'VARCHAR',
                                                   'cache_read_tokens': 'VARCHAR',
                                                   'cache_creation_tokens': 'VARCHAR',
                                                   'decision': 'VARCHAR', 'decision_source': 'VARCHAR',
                                                   'tool_name': 'VARCHAR', 'success': 'VARCHAR',
                                                   'error_message': 'VARCHAR', 'status_code': 'VARCHAR',
                                                   'prompt_length': 'VARCHAR'}})
        """)
    finally:
        staging_csv.unlink(missing_ok=True)

    total = con.execute("SELECT COUNT(*) FROM stg_events").fetchone()[0]
    log("INGEST", f"stg_events: {total:,} rows staged")
    return parse_errors


# ---------------------------------------------------------------------------
# 4. Load fact tables with TRY_CAST validation
# ---------------------------------------------------------------------------
def load_fact_api_requests(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        INSERT INTO fact_api_requests
        SELECT
            epoch_ms,
            session_id,
            user_email,
            model,
            TRY_CAST(cost_usd AS DOUBLE)           AS cost_usd,
            TRY_CAST(duration_ms AS BIGINT)         AS duration_ms,
            TRY_CAST(input_tokens AS BIGINT)        AS input_tokens,
            TRY_CAST(output_tokens AS BIGINT)       AS output_tokens,
            TRY_CAST(cache_read_tokens AS BIGINT)   AS cache_read_tokens,
            TRY_CAST(cache_creation_tokens AS BIGINT) AS cache_creation_tokens
        FROM stg_events
        WHERE body = 'claude_code.api_request'
    """)
    total = con.execute("SELECT COUNT(*) FROM fact_api_requests").fetchone()[0]

    # Validation: count rows where TRY_CAST produced NULL on required numeric fields
    rejected = con.execute("""
        SELECT COUNT(*) FROM fact_api_requests
        WHERE cost_usd IS NULL
           OR duration_ms IS NULL
           OR input_tokens IS NULL
           OR output_tokens IS NULL
    """).fetchone()[0]

    log("INGEST", f"fact_api_requests: {total:,} loaded, {rejected:,} rejected (NULL from TRY_CAST)")


def load_fact_tool_usage(con: duckdb.DuckDBPyConnection) -> None:
    # tool_decision events provide decision + decision_source
    # tool_result events provide success + duration_ms
    # We union them into fact_tool_usage, filling missing fields with NULL

    con.execute("""
        INSERT INTO fact_tool_usage
        SELECT
            epoch_ms,
            session_id,
            user_email,
            tool_name,
            decision,
            decision_source,
            NULL AS is_success,
            NULL AS duration_ms
        FROM stg_events
        WHERE body = 'claude_code.tool_decision'
    """)

    con.execute("""
        INSERT INTO fact_tool_usage
        SELECT
            epoch_ms,
            session_id,
            user_email,
            tool_name,
            decision AS decision,
            decision_source,
            CASE WHEN success = 'true' THEN TRUE
                 WHEN success = 'false' THEN FALSE
                 ELSE NULL END AS is_success,
            TRY_CAST(duration_ms AS BIGINT) AS duration_ms
        FROM stg_events
        WHERE body = 'claude_code.tool_result'
    """)

    total = con.execute("SELECT COUNT(*) FROM fact_tool_usage").fetchone()[0]
    decisions = con.execute(
        "SELECT COUNT(*) FROM fact_tool_usage WHERE decision IS NOT NULL AND decision != ''"
    ).fetchone()[0]
    results = con.execute(
        "SELECT COUNT(*) FROM fact_tool_usage WHERE is_success IS NOT NULL"
    ).fetchone()[0]
    log("INGEST", f"fact_tool_usage: {total:,} loaded ({decisions:,} decisions, {results:,} results)")


def load_fact_api_errors(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        INSERT INTO fact_api_errors
        SELECT
            epoch_ms,
            session_id,
            user_email,
            model,
            error_message,
            TRY_CAST(status_code AS INTEGER) AS status_code
        FROM stg_events
        WHERE body = 'claude_code.api_error'
    """)
    total = con.execute("SELECT COUNT(*) FROM fact_api_errors").fetchone()[0]
    bad_status = con.execute(
        "SELECT COUNT(*) FROM fact_api_errors WHERE status_code IS NULL"
    ).fetchone()[0]
    log("INGEST", f"fact_api_errors: {total:,} loaded, {bad_status:,} with NULL status_code")


def load_fact_user_prompts(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        INSERT INTO fact_user_prompts
        SELECT
            epoch_ms,
            session_id,
            user_email,
            TRY_CAST(prompt_length AS BIGINT) AS prompt_length
        FROM stg_events
        WHERE body = 'claude_code.user_prompt'
    """)
    total = con.execute("SELECT COUNT(*) FROM fact_user_prompts").fetchone()[0]
    bad_len = con.execute(
        "SELECT COUNT(*) FROM fact_user_prompts WHERE prompt_length IS NULL"
    ).fetchone()[0]
    log("INGEST", f"fact_user_prompts: {total:,} loaded, {bad_len:,} with NULL prompt_length")


# ---------------------------------------------------------------------------
# 5. Cross-table validation
# ---------------------------------------------------------------------------
def validate_orphans(con: duckdb.DuckDBPyConnection) -> None:
    """Check for user_email values in fact tables not present in dim_employees."""
    fact_tables = ["fact_api_requests", "fact_tool_usage", "fact_api_errors", "fact_user_prompts"]

    for table in fact_tables:
        orphans = con.execute(f"""
            SELECT DISTINCT f.user_email
            FROM {table} f
            LEFT JOIN dim_employees e ON f.user_email = e.email
            WHERE e.email IS NULL
              AND f.user_email IS NOT NULL
              AND f.user_email != ''
        """).fetchall()

        if orphans:
            emails = [r[0] for r in orphans]
            log("VALIDATE", f"{table}: {len(emails)} orphaned email(s): {emails[:5]}")
        else:
            log("VALIDATE", f"{table}: all emails matched in dim_employees ✓")


# ---------------------------------------------------------------------------
# 6. Cleanup staging
# ---------------------------------------------------------------------------
def cleanup_staging(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("DROP TABLE IF EXISTS stg_events")
    log("CLEANUP", "Dropped stg_events staging table")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run_pipeline() -> None:
    log("PIPELINE", "=" * 60)
    log("PIPELINE", "Claude Code Telemetry Ingestion Pipeline")
    log("PIPELINE", "=" * 60)
    t0 = time.time()

    con = get_connection()

    create_schema(con)
    load_employees(con)
    parse_errors = load_raw_events(con)

    load_fact_api_requests(con)
    load_fact_tool_usage(con)
    load_fact_api_errors(con)
    load_fact_user_prompts(con)

    validate_orphans(con)
    cleanup_staging(con)

    elapsed = time.time() - t0
    log("PIPELINE", f"Completed in {elapsed:.1f}s (parse errors: {parse_errors:,})")
    log("PIPELINE", f"Database: {DB_PATH}")

    con.close()


if __name__ == "__main__":
    run_pipeline()
