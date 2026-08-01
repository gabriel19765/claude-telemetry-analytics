#!/usr/bin/env python3
"""Telemetry Analyzer — Custom agent skill for querying telemetry.duckdb.

Usage:
    python agent/skills/telemetry_analyzer.py "SELECT COUNT(*) FROM fact_api_requests"
    python agent/skills/telemetry_analyzer.py --tables
    python agent/skills/telemetry_analyzer.py --schema fact_api_requests
"""

import argparse
import json
import sys
from pathlib import Path

import duckdb

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "telemetry.duckdb"


def get_connection() -> duckdb.DuckDBPyConnection:
    if not DB_PATH.exists():
        print(f"[ERROR] Database not found at {DB_PATH}", file=sys.stderr)
        print("[ERROR] Run the ingestion pipeline first: python src/ingestion.py", file=sys.stderr)
        sys.exit(1)
    return duckdb.connect(str(DB_PATH), read_only=True)


def list_tables(con: duckdb.DuckDBPyConnection) -> None:
    """List all tables with row counts."""
    tables = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' ORDER BY table_name"
    ).fetchall()
    result = []
    for (table_name,) in tables:
        count = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        result.append({"table": table_name, "rows": count})
    print(json.dumps(result, indent=2))


def show_schema(con: duckdb.DuckDBPyConnection, table_name: str) -> None:
    """Show column names and types for a table."""
    try:
        columns = con.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = ? ORDER BY ordinal_position",
            [table_name],
        ).fetchall()
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    if not columns:
        print(f"[ERROR] Table '{table_name}' not found.", file=sys.stderr)
        sys.exit(1)

    result = [{"column": name, "type": dtype} for name, dtype in columns]
    print(json.dumps(result, indent=2))


def run_query(con: duckdb.DuckDBPyConnection, sql: str) -> None:
    """Execute an arbitrary SQL query and return JSON results."""
    try:
        result = con.execute(sql)
        columns = [desc[0] for desc in result.description]
        rows = result.fetchall()
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

    output = [dict(zip(columns, row)) for row in rows]

    # Truncate large result sets for readability
    if len(output) > 100:
        print(f"[INFO] Showing first 100 of {len(output)} rows.", file=sys.stderr)
        output = output[:100]

    # Custom serializer for types that json can't handle natively
    def default_serializer(obj):
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        if isinstance(obj, (bytes, bytearray)):
            return obj.hex()
        return str(obj)

    print(json.dumps(output, indent=2, default=default_serializer))


def main() -> None:
    parser = argparse.ArgumentParser(description="Query telemetry.duckdb")
    parser.add_argument("query", nargs="?", help="SQL query to execute")
    parser.add_argument("--tables", action="store_true", help="List all tables with row counts")
    parser.add_argument("--schema", type=str, help="Show schema for a table")
    args = parser.parse_args()

    if not any([args.query, args.tables, args.schema]):
        parser.print_help()
        sys.exit(1)

    con = get_connection()

    if args.tables:
        list_tables(con)
    elif args.schema:
        show_schema(con, args.schema)
    elif args.query:
        run_query(con, args.query)

    con.close()


if __name__ == "__main__":
    main()
