"""
analysis.py – Time series analysis helpers: rolling averages, trend lines,
autocorrelation, and anomaly detection.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

try:
    from statsmodels.tsa.stattools import acf
    _HAS_STATSMODELS = True
except ImportError:
    _HAS_STATSMODELS = False


# ---------------------------------------------------------------------------
# Chart D – rolling average with anomaly highlighting
# ---------------------------------------------------------------------------

def build_rolling_avg_chart(
    df: pd.DataFrame,
    window: int = 4,
    anomaly_std_threshold: float = 2.0,
) -> go.Figure:
    """
    Chart D – weekly visit count with rolling average and ±1 std band.

    df columns: arrived_at (datetime), imo (str)
    Anomalies: weeks where count > rolling_mean + anomaly_std_threshold * rolling_std.
    """
    if df.empty:
        fig = go.Figure()
        fig.update_layout(title="No data available", template="plotly_dark")
        return fig

    df = df.copy()
    df["week"] = pd.to_datetime(df["arrived_at"]).dt.to_period("W").dt.start_time
    weekly = df.groupby("week").size().reset_index(name="visits").sort_values("week")
    weekly = weekly.set_index("week")

    weekly["rolling_mean"] = weekly["visits"].rolling(window, min_periods=1).mean()
    weekly["rolling_std"] = weekly["visits"].rolling(window, min_periods=1).std().fillna(0)
    weekly["upper"] = weekly["rolling_mean"] + weekly["rolling_std"]
    weekly["lower"] = (weekly["rolling_mean"] - weekly["rolling_std"]).clip(lower=0)

    anomaly_mask = weekly["visits"] > (
        weekly["rolling_mean"] + anomaly_std_threshold * weekly["rolling_std"]
    )
    anomalies = weekly[anomaly_mask]

    fig = go.Figure()

    # ±1 std band
    fig.add_trace(go.Scatter(
        x=weekly.index.tolist() + weekly.index.tolist()[::-1],
        y=weekly["upper"].tolist() + weekly["lower"].tolist()[::-1],
        fill="toself",
        fillcolor="rgba(52,152,219,0.15)",
        line=dict(color="rgba(255,255,255,0)"),
        hoverinfo="skip",
        name="±1 std",
        showlegend=True,
    ))

    # Weekly counts
    fig.add_trace(go.Bar(
        x=weekly.index, y=weekly["visits"],
        name="Weekly visits",
        marker_color="rgba(52,152,219,0.6)",
    ))

    # Rolling mean
    fig.add_trace(go.Scatter(
        x=weekly.index, y=weekly["rolling_mean"],
        name=f"{window}w rolling avg",
        mode="lines",
        line=dict(color="#F39C12", width=2),
    ))

    # Anomalies
    if not anomalies.empty:
        fig.add_trace(go.Scatter(
            x=anomalies.index, y=anomalies["visits"],
            mode="markers",
            marker=dict(color="#E74C3C", size=10, symbol="x"),
            name="Anomaly",
        ))

    fig.update_layout(
        title="Weekly visit count – rolling average & anomalies",
        xaxis_title="Week",
        yaxis_title="Visits",
        template="plotly_dark",
        barmode="overlay",
    )
    return fig


# ---------------------------------------------------------------------------
# Chart E – heatmap port × week
# ---------------------------------------------------------------------------

def build_heatmap(df: pd.DataFrame, top_n_ports: int = 10) -> go.Figure:
    """
    Chart E – heatmap of visit counts: port (y) × week (x).

    df columns: arrived_at, port_name
    """
    if df.empty:
        fig = go.Figure()
        fig.update_layout(title="No data available", template="plotly_dark")
        return fig

    df = df.copy()
    df["week"] = pd.to_datetime(df["arrived_at"]).dt.to_period("W").dt.start_time

    # Pick top N ports by total visits
    top_ports = (
        df.groupby("port_name").size()
        .nlargest(top_n_ports)
        .index.tolist()
    )
    df_top = df[df["port_name"].isin(top_ports)]

    pivot = (
        df_top.groupby(["port_name", "week"])
        .size()
        .unstack("week", fill_value=0)
    )

    fig = go.Figure(go.Heatmap(
        z=pivot.values.tolist(),
        x=[str(c)[:10] for c in pivot.columns],
        y=pivot.index.tolist(),
        colorscale="Blues",
        hoverongaps=False,
        colorbar=dict(title="Visits"),
    ))

    fig.update_layout(
        title="Port × week visit heatmap (top ports)",
        xaxis_title="Week",
        yaxis_title="Port",
        template="plotly_dark",
    )
    return fig


# ---------------------------------------------------------------------------
# Chart F – autocorrelation
# ---------------------------------------------------------------------------

def build_autocorrelation(df: pd.DataFrame, nlags: int = 20) -> go.Figure:
    """
    Chart F – autocorrelation of weekly visit frequency.

    df columns: arrived_at
    """
    if df.empty or not _HAS_STATSMODELS:
        fig = go.Figure()
        msg = "No data available" if df.empty else "statsmodels not installed"
        fig.update_layout(title=msg, template="plotly_dark")
        return fig

    df = df.copy()
    df["week"] = pd.to_datetime(df["arrived_at"]).dt.to_period("W").dt.start_time
    weekly = df.groupby("week").size()

    if len(weekly) < nlags + 1:
        nlags = max(1, len(weekly) - 1)

    acf_vals, conf_int = acf(weekly.values, nlags=nlags, alpha=0.05)
    lags = list(range(nlags + 1))
    ci_upper = conf_int[:, 1] - acf_vals
    ci_lower = acf_vals - conf_int[:, 0]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=lags, y=acf_vals.tolist(),
        name="ACF",
        marker_color="rgba(52,152,219,0.7)",
        error_y=dict(
            type="data",
            symmetric=False,
            array=ci_upper.tolist(),
            arrayminus=ci_lower.tolist(),
            visible=True,
        ),
    ))
    fig.add_hline(y=0, line_color="white", line_dash="dash")

    fig.update_layout(
        title="Autocorrelation of weekly visit frequency",
        xaxis_title="Lag (weeks)",
        yaxis_title="ACF",
        template="plotly_dark",
    )
    return fig
