"""Multi-persona Streamlit dashboard for Claude Code telemetry analytics.

Three views:
1. Engineering Lead / CTO — Costs, Efficiency & Governance
2. Product Manager — Claude Code Adoption & Tool Analytics
3. Developer Insights — Performance & Operational Health
"""

import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from src import analytics, ml

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Claude Code Telemetry Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Theme / color palette
# ---------------------------------------------------------------------------
PALETTE = {
    "primary": "#6366F1",       # Indigo
    "secondary": "#8B5CF6",     # Violet
    "success": "#10B981",       # Emerald
    "warning": "#F59E0B",       # Amber
    "danger": "#EF4444",        # Red
    "info": "#3B82F6",          # Blue
    "surface": "#1E1E2E",       # Dark surface
}
PRACTICE_COLORS = {
    "Frontend Engineering": "#6366F1",
    "Backend Engineering": "#8B5CF6",
    "Data Engineering": "#3B82F6",
    "ML Engineering": "#10B981",
    "Platform Engineering": "#F59E0B",
}
MODEL_COLORS = {
    "claude-haiku-4-5-20251001": "#10B981",
    "claude-sonnet-4-5-20250929": "#6366F1",
    "claude-sonnet-4-6": "#818CF8",
    "claude-opus-4-5-20251101": "#F59E0B",
    "claude-opus-4-6": "#F97316",
}


def format_usd(val: float) -> str:
    return f"${val:,.2f}"


def format_pct(val: float) -> str:
    return f"{val:.1f}%"


def format_number(val: int | float) -> str:
    return f"{val:,.0f}"


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("📊 Telemetry Analytics")
st.sidebar.markdown("---")
persona = st.sidebar.radio(
    "Select View",
    [
        "🏗️ Engineering Lead / CTO",
        "📦 Product Manager",
        "🔧 Developer Insights",
    ],
    index=0,
)
st.sidebar.markdown("---")
st.sidebar.caption("Claude Code Usage Analytics Platform")
st.sidebar.caption("Data: DuckDB • Charts: Plotly")


# ---------------------------------------------------------------------------
# DB connection (cached)
# ---------------------------------------------------------------------------
@st.cache_resource
def get_con():
    return analytics.get_connection()


con = get_con()


# ===================================================================
# PERSONA 1: Engineering Lead / CTO
# ===================================================================
if persona == "🏗️ Engineering Lead / CTO":
    st.title("🏗️ Engineering Lead / CTO Dashboard")
    st.caption("Costs, Efficiency & Governance")

    # --- Top-level KPIs ---
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Simulated Cost", format_usd(analytics.total_cost(con)))
    with col2:
        st.metric("Total Tokens", format_number(analytics.total_tokens(con)))
    with col3:
        st.metric("Cache Read Ratio", format_pct(analytics.cache_read_ratio(con)))
    with col4:
        st.metric("API Error Rate", format_pct(analytics.api_error_rate(con)))

    st.markdown("---")

    # --- Cost by Practice ---
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Cost Distribution by Practice")
        df_practice = analytics.cost_by_practice(con)
        if not df_practice.empty:
            fig = px.bar(
                df_practice,
                x="practice",
                y="total_cost",
                color="practice",
                color_discrete_map=PRACTICE_COLORS,
                text_auto="$.2f",
                labels={"total_cost": "Total Cost ($)", "practice": "Practice"},
            )
            fig.update_layout(showlegend=False, height=400)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No data available.")

    with col_right:
        st.subheader("Cost Distribution by Seniority Level")
        df_level = analytics.cost_by_level(con)
        if not df_level.empty:
            fig = px.bar(
                df_level,
                x="level",
                y="total_cost",
                color="level",
                text_auto="$.2f",
                labels={"total_cost": "Total Cost ($)", "level": "Level"},
                color_discrete_sequence=px.colors.sequential.Viridis,
            )
            fig.update_layout(showlegend=False, height=400)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No data available.")

    # --- Token Efficiency ---
    st.subheader("Token Efficiency & Cache Utilization by Practice")
    df_eff = analytics.token_efficiency_by_practice(con)
    if not df_eff.empty:
        col_a, col_b = st.columns(2)
        with col_a:
            fig = px.bar(
                df_eff,
                x="practice",
                y="cache_hit_pct",
                color="practice",
                color_discrete_map=PRACTICE_COLORS,
                labels={"cache_hit_pct": "Cache Hit %", "practice": "Practice"},
                text_auto=".1f",
            )
            fig.update_layout(showlegend=False, height=350, title="Cache Hit Rate by Practice")
            st.plotly_chart(fig, use_container_width=True)

        with col_b:
            fig = px.bar(
                df_eff,
                x="practice",
                y="avg_duration_ms",
                color="practice",
                color_discrete_map=PRACTICE_COLORS,
                labels={"avg_duration_ms": "Avg Duration (ms)", "practice": "Practice"},
                text_auto=",.0f",
            )
            fig.update_layout(showlegend=False, height=350, title="Avg API Duration by Practice")
            st.plotly_chart(fig, use_container_width=True)

        st.dataframe(df_eff, use_container_width=True, hide_index=True)


# ===================================================================
# PERSONA 2: Product Manager
# ===================================================================
elif persona == "📦 Product Manager":
    st.title("📦 Product Manager Dashboard")
    st.caption("Claude Code Adoption & Tool Analytics")

    # --- Model Adoption ---
    st.subheader("Model Adoption Breakdown")
    df_models = analytics.model_usage_breakdown(con)
    if not df_models.empty:
        col1, col2 = st.columns(2)
        with col1:
            fig = px.pie(
                df_models,
                names="model",
                values="request_count",
                color="model",
                color_discrete_map=MODEL_COLORS,
                title="Requests by Model",
            )
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            fig = px.bar(
                df_models,
                x="model",
                y="total_cost",
                color="model",
                color_discrete_map=MODEL_COLORS,
                text_auto="$.2f",
                title="Cost by Model",
                labels={"total_cost": "Total Cost ($)", "model": "Model"},
            )
            fig.update_layout(showlegend=False, height=400)
            st.plotly_chart(fig, use_container_width=True)

        st.dataframe(df_models, use_container_width=True, hide_index=True)

    st.markdown("---")

    # --- Tool Usage ---
    st.subheader("Tool Usage Frequency & Rejection Rates")
    df_tools = analytics.tool_usage_frequency(con)
    if not df_tools.empty:
        col1, col2 = st.columns(2)
        with col1:
            fig = px.bar(
                df_tools,
                x="tool_name",
                y="usage_count",
                color="tool_name",
                text_auto=True,
                title="Tool Usage Count (Decisions)",
                labels={"usage_count": "Count", "tool_name": "Tool"},
            )
            fig.update_layout(showlegend=False, height=400)
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            fig = px.bar(
                df_tools,
                x="tool_name",
                y="reject_rate_pct",
                color="reject_rate_pct",
                color_continuous_scale="Reds",
                text_auto=".1f",
                title="Rejection Rate by Tool (%)",
                labels={"reject_rate_pct": "Reject %", "tool_name": "Tool"},
            )
            fig.update_layout(showlegend=False, height=400)
            st.plotly_chart(fig, use_container_width=True)

    # --- Tool Success Rates ---
    st.subheader("Tool Execution Success Rates & Latency")
    df_success = analytics.tool_success_rates(con)
    if not df_success.empty:
        col1, col2 = st.columns(2)
        with col1:
            fig = px.bar(
                df_success,
                x="tool_name",
                y="success_rate_pct",
                color="success_rate_pct",
                color_continuous_scale="Greens",
                text_auto=".1f",
                title="Success Rate by Tool (%)",
                labels={"success_rate_pct": "Success %", "tool_name": "Tool"},
            )
            fig.update_layout(showlegend=False, height=400)
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=df_success["tool_name"],
                y=df_success["avg_duration_ms"],
                name="Avg",
                marker_color=PALETTE["info"],
            ))
            fig.add_trace(go.Bar(
                x=df_success["tool_name"],
                y=df_success["p95_duration_ms"],
                name="P95",
                marker_color=PALETTE["warning"],
            ))
            fig.update_layout(
                barmode="group",
                title="Tool Latency: Avg vs P95 (ms)",
                yaxis_title="Duration (ms)",
                height=400,
            )
            st.plotly_chart(fig, use_container_width=True)

        st.dataframe(df_success, use_container_width=True, hide_index=True)

    # --- Tool latency distribution box plots ---
    st.subheader("Tool Latency Distribution")
    df_latency = analytics.tool_latency_distribution(con)
    if not df_latency.empty:
        fig = px.box(
            df_latency,
            x="tool_name",
            y="duration_ms",
            color="tool_name",
            title="Execution Time Distribution by Tool",
            labels={"duration_ms": "Duration (ms)", "tool_name": "Tool"},
        )
        fig.update_layout(showlegend=False, height=450)
        st.plotly_chart(fig, use_container_width=True)


# ===================================================================
# PERSONA 3: Developer Insights
# ===================================================================
elif persona == "🔧 Developer Insights":
    st.title("🔧 Developer Insights Dashboard")
    st.caption("Performance & Operational Health")

    # --- API Errors ---
    st.subheader("Common API Errors")
    df_errors = analytics.common_api_errors(con)
    if not df_errors.empty:
        col1, col2 = st.columns(2)
        with col1:
            # Group by status code
            df_by_status = df_errors.groupby("status_code", as_index=False).agg(
                {"error_count": "sum", "affected_users": "sum"}
            )
            fig = px.bar(
                df_by_status,
                x="status_code",
                y="error_count",
                color="status_code",
                text_auto=True,
                title="Errors by Status Code",
                labels={"error_count": "Count", "status_code": "HTTP Status"},
                color_discrete_sequence=px.colors.sequential.Reds_r,
            )
            fig.update_layout(showlegend=False, height=400)
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            df_model_err = analytics.error_rate_by_model(con)
            if not df_model_err.empty:
                fig = px.bar(
                    df_model_err,
                    x="model",
                    y="error_rate_pct",
                    color="model",
                    color_discrete_map=MODEL_COLORS,
                    text_auto=".1f",
                    title="Error Rate by Model (%)",
                    labels={"error_rate_pct": "Error Rate %", "model": "Model"},
                )
                fig.update_layout(showlegend=False, height=400)
                st.plotly_chart(fig, use_container_width=True)

        st.dataframe(df_errors, use_container_width=True, hide_index=True)

    st.markdown("---")

    # --- Session Interaction Stats ---
    st.subheader("Session Interaction Analysis")
    df_sessions = analytics.session_interaction_stats(con)
    if not df_sessions.empty:
        col1, col2 = st.columns(2)
        with col1:
            avg_turns = df_sessions["prompt_count"].mean()
            median_turns = df_sessions["prompt_count"].median()
            st.metric("Avg Prompts per Session", f"{avg_turns:.1f}")
            st.metric("Median Prompts per Session", f"{median_turns:.0f}")

            fig = px.histogram(
                df_sessions,
                x="prompt_count",
                nbins=30,
                title="Distribution of Interaction Turns per Session",
                labels={"prompt_count": "Prompts per Session", "count": "Sessions"},
                color_discrete_sequence=[PALETTE["primary"]],
            )
            fig.update_layout(height=350)
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            df_prompt_len = analytics.prompt_length_distribution(con)
            if not df_prompt_len.empty:
                avg_len = df_prompt_len["prompt_length"].mean()
                st.metric("Avg Prompt Length (chars)", format_number(avg_len))

                fig = px.histogram(
                    df_prompt_len,
                    x="prompt_length",
                    nbins=50,
                    title="Prompt Length Distribution",
                    labels={"prompt_length": "Prompt Length (chars)", "count": "Count"},
                    color_discrete_sequence=[PALETTE["secondary"]],
                )
                fig.update_layout(height=350)
                st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # --- High Latency Tools ---
    st.subheader("High-Latency Tool Identification")
    df_lat = analytics.high_latency_tools(con)
    if not df_lat.empty:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=df_lat["tool_name"], y=df_lat["p50_ms"], name="P50", marker_color=PALETTE["success"]))
        fig.add_trace(go.Bar(x=df_lat["tool_name"], y=df_lat["p95_ms"], name="P95", marker_color=PALETTE["warning"]))
        fig.add_trace(go.Bar(x=df_lat["tool_name"], y=df_lat["p99_ms"], name="P99", marker_color=PALETTE["danger"]))
        fig.update_layout(
            barmode="group",
            title="Tool Latency Percentiles (ms)",
            yaxis_title="Duration (ms)",
            height=450,
        )
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df_lat, use_container_width=True, hide_index=True)

    # --- API Latency by Model ---
    st.subheader("API Request Latency by Model")
    df_api_lat = analytics.api_request_latency_by_model(con)
    if not df_api_lat.empty:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=df_api_lat["model"], y=df_api_lat["avg_ms"], name="Avg", marker_color=PALETTE["info"]))
        fig.add_trace(go.Bar(x=df_api_lat["model"], y=df_api_lat["p50_ms"], name="P50", marker_color=PALETTE["success"]))
        fig.add_trace(go.Bar(x=df_api_lat["model"], y=df_api_lat["p95_ms"], name="P95", marker_color=PALETTE["warning"]))
        fig.update_layout(
            barmode="group",
            title="API Latency by Model (ms)",
            yaxis_title="Duration (ms)",
            height=400,
        )
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df_api_lat, use_container_width=True, hide_index=True)

    st.markdown("---")

    # --- ML Anomaly Detection ---
    st.subheader("🤖 ML Statistical Anomaly Detection")
    st.caption("Automated detection of abnormal usage spikes, runaway costs, and severe tool latency degradation.")

    with st.expander("ℹ️ How Anomaly Detection Works (Click to Expand)", expanded=False):
        st.markdown("""
        - **Cost Anomalies (Z-Score Thresholding)**: Calculates the standard deviation of API request costs. Any request exceeding **+3.0 Standard Deviations** above the mean cost is flagged as a statistical outlier.
        - **Tool Latency Anomalies (IQR Method)**: Computes the 75th percentile ($Q3$) and Interquartile Range ($IQR = Q3 - Q1$) per tool. Any tool execution taking longer than $Q3 + 1.5 \\times IQR$ is flagged as a severe latency bottleneck.
        """)

    summary = ml.get_anomaly_summary(con)
    kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
    with kpi_col1:
        st.metric("🚨 Cost Anomalies", format_number(summary["cost_anomaly_count"]))
    with kpi_col2:
        st.metric("💸 Impacted Cost", format_usd(summary["total_anomalous_cost_usd"]))
    with kpi_col3:
        st.metric("⏱️ Tool Latency Outliers", format_number(summary["latency_anomaly_count"]))
    with kpi_col4:
        st.metric("⏳ Max Latency Spike", f"{summary['max_latency_sec']:,}s")

    st.markdown("### Detailed Outlier Inspection")
    col_anom1, col_anom2 = st.columns(2)

    with col_anom1:
        st.markdown("##### 1. High Cost Outliers (Z-Score > 3.0)")
        df_cost_anom = ml.detect_cost_anomalies(con, z_threshold=3.0)
        if not df_cost_anom.empty:
            fig_anom_cost = px.scatter(
                df_cost_anom.head(50),
                x="z_score",
                y="cost_usd",
                color="model",
                hover_data=["user_email", "timestamp"],
                title="Cost ($) vs Z-Score Severity",
                labels={"z_score": "Z-Score (Std Devs)", "cost_usd": "Cost ($USD)"},
                color_discrete_map=MODEL_COLORS,
            )
            fig_anom_cost.update_layout(height=350)
            st.plotly_chart(fig_anom_cost, use_container_width=True)

            st.dataframe(
                df_cost_anom[["timestamp", "user_email", "model", "cost_usd", "duration_sec", "z_score"]],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.success("No extreme cost anomalies detected.")

    with col_anom2:
        st.markdown("##### 2. Severe Tool Latency Outliers (IQR)")
        df_lat_anom = ml.detect_latency_anomalies(con, iqr_multiplier=1.5)
        if not df_lat_anom.empty:
            fig_anom_lat = px.bar(
                df_lat_anom.head(15),
                x="tool_name",
                y="duration_sec",
                color="tool_name",
                hover_data=["user_email", "timestamp"],
                title="Top Tool Latency Spikes (Seconds)",
                labels={"duration_sec": "Duration (Seconds)", "tool_name": "Tool"},
            )
            fig_anom_lat.update_layout(showlegend=False, height=350)
            st.plotly_chart(fig_anom_lat, use_container_width=True)

            st.dataframe(
                df_lat_anom[["timestamp", "user_email", "tool_name", "duration_sec", "threshold_sec"]],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.success("No latency outliers detected.")


