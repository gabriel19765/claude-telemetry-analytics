# Telemetry Analytics — Architecture & Coding Rules

## Data Architecture

### Storage
- **OLAP Engine**: DuckDB (embedded, columnar, zero-config)
- **Schema**: Star schema with one dimension table (`dim_employees`) and four fact tables
- **Location**: `data/telemetry.duckdb` — generated at runtime, gitignored

### Source Data
- `output/telemetry_logs.jsonl`: CloudWatch log batches. Each line is a JSON object with `logEvents[]` array. Each event's `message` field is a **stringified JSON** containing the OTel event.
- `output/employees.csv`: Employee metadata (email, full_name, practice, level, location)

### Event Types (in `message.body`)
| Body Value | Fact Table | Key Attributes |
|---|---|---|
| `claude_code.api_request` | `fact_api_requests` | model, cost_usd, duration_ms, input/output/cache tokens |
| `claude_code.tool_decision` | `fact_tool_usage` | tool_name, decision, source |
| `claude_code.tool_result` | `fact_tool_usage` | tool_name, success, duration_ms |
| `claude_code.api_error` | `fact_api_errors` | model, error, status_code |
| `claude_code.user_prompt` | `fact_user_prompts` | prompt_length |

### Table Schemas

#### `dim_employees`
```sql
CREATE OR REPLACE TABLE dim_employees (
    email       VARCHAR PRIMARY KEY,
    full_name   VARCHAR,
    practice    VARCHAR,
    level       VARCHAR,
    location    VARCHAR
);
```

#### `fact_api_requests`
```sql
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
);
```

#### `fact_tool_usage`
```sql
CREATE OR REPLACE TABLE fact_tool_usage (
    epoch_ms         BIGINT,
    session_id       VARCHAR,
    user_email       VARCHAR,
    tool_name        VARCHAR,
    decision         VARCHAR,
    decision_source  VARCHAR,
    is_success       BOOLEAN,
    duration_ms      BIGINT
);
```

#### `fact_api_errors`
```sql
CREATE OR REPLACE TABLE fact_api_errors (
    epoch_ms       BIGINT,
    session_id     VARCHAR,
    user_email     VARCHAR,
    model          VARCHAR,
    error_message  VARCHAR,
    status_code    INTEGER
);
```

#### `fact_user_prompts`
```sql
CREATE OR REPLACE TABLE fact_user_prompts (
    epoch_ms       BIGINT,
    session_id     VARCHAR,
    user_email     VARCHAR,
    prompt_length  BIGINT
);
```

## Coding Constraints

1. **Idempotency**: All table creation uses `CREATE OR REPLACE TABLE`. Pipeline can be re-run safely.
2. **Safe Casting**: Use `TRY_CAST(value AS type)` for all numeric/boolean conversions from string fields. Never use bare `CAST` on user-supplied data.
3. **Validation**: After each table load, count rows where `TRY_CAST` produced NULL on a required field. Log rejected count explicitly.
4. **Orphan Detection**: After loading fact tables, check for `user_email` values not present in `dim_employees`. Log them.
5. **No Silent Failures**: Every parse/cast error must be counted and logged. Do not catch exceptions silently.
6. **Vectorized Operations**: Prefer DuckDB SQL over Python loops for data transformation. Use `read_json_auto`, `json_extract_string`, and `unnest` where possible.
7. **Structured Logging**: Use `[INGEST]`, `[ANALYTICS]`, `[VALIDATE]` prefixes in log output.

## Dashboard Rules
- Use Plotly for all charts (no matplotlib)
- Streamlit sidebar for persona selection
- All monetary values formatted as USD with 2 decimal places
- All percentages with 1 decimal place
- Color palette: consistent across all personas
