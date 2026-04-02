"""
port_ts.py – Port visit time series chart helpers.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from tankerwatch.app.map_view import VESSEL_TYPE_COLOURS


def _week_label(dt: pd.Timestamp) -> str:
    return dt.strftime("%Y-W%V")


def build_stacked_bar(df: pd.DataFrame) -> go.Figure:
    """
    Chart A – weekly vessel visits stacked by vessel type.

    df columns: arrived_at (datetime), vessel_type (str), imo (str)
    """
    if df.empty:
        fig = go.Figure()
        fig.update_layout(title="No data available", template="plotly_dark")
        return fig

    df = df.copy()
    df["week"] = pd.to_datetime(df["arrived_at"]).dt.to_period("W").dt.start_time
    counts = df.groupby(["week", "vessel_type"]).size().reset_index(name="visits")

    fig = go.Figure()
    for vtype in sorted(counts["vessel_type"].unique()):
        sub = counts[counts["vessel_type"] == vtype]
        fig.add_trace(go.Bar(
            x=sub["week"],
            y=sub["visits"],
            name=vtype,
            marker_color=VESSEL_TYPE_COLOURS.get(vtype, "#BDC3C7"),
        ))

    fig.update_layout(
        barmode="stack",
        title="Weekly vessel visits by type",
        xaxis_title="Week",
        yaxis_title="Visits",
        template="plotly_dark",
        legend_title="Vessel type",
    )
    return fig


def build_line_chart(df: pd.DataFrame) -> go.Figure:
    """
    Chart B – unique vessel count per week by type, with secondary y-axis for total DWT.

    df columns: arrived_at, vessel_type, imo, dwt
    """
    if df.empty:
        fig = go.Figure()
        fig.update_layout(title="No data available", template="plotly_dark")
        return fig

    df = df.copy()
    df["week"] = pd.to_datetime(df["arrived_at"]).dt.to_period("W").dt.start_time

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    for vtype in sorted(df["vessel_type"].unique()):
        sub = df[df["vessel_type"] == vtype].groupby("week")["imo"].nunique().reset_index(name="unique_vessels")
        fig.add_trace(
            go.Scatter(
                x=sub["week"], y=sub["unique_vessels"],
                name=vtype, mode="lines+markers",
                marker_color=VESSEL_TYPE_COLOURS.get(vtype, "#BDC3C7"),
            ),
            secondary_y=False,
        )

    # Total DWT secondary axis
    dwt_weekly = df.groupby("week")["dwt"].sum().reset_index()
    fig.add_trace(
        go.Scatter(
            x=dwt_weekly["week"], y=dwt_weekly["dwt"],
            name="Total DWT", mode="lines",
            line=dict(color="rgba(255,255,255,0.3)", dash="dot"),
        ),
        secondary_y=True,
    )

    fig.update_layout(
        title="Unique vessel count per week",
        template="plotly_dark",
        legend_title="Vessel type",
    )
    fig.update_yaxes(title_text="Unique vessels", secondary_y=False)
    fig.update_yaxes(title_text="Total DWT (capacity)", secondary_y=True)
    return fig


def build_visit_scatter(df: pd.DataFrame) -> go.Figure:
    """
    Chart C – individual vessel visits on a timeline.

    df columns: arrived_at, vessel_type, imo, vessel_name, dwt, departed_at
    """
    if df.empty:
        fig = go.Figure()
        fig.update_layout(title="No data available", template="plotly_dark")
        return fig

    df = df.copy()
    df["arrived_at"] = pd.to_datetime(df["arrived_at"])
    df["departed_at"] = pd.to_datetime(df["departed_at"])
    df["duration_h"] = (
        (df["departed_at"] - df["arrived_at"]).dt.total_seconds() / 3600
    ).fillna(0).clip(lower=0)

    fig = go.Figure()
    for vtype in sorted(df["vessel_type"].unique()):
        sub = df[df["vessel_type"] == vtype]
        sizes = (sub["dwt"].fillna(50000) / 20000).clip(lower=3, upper=20)
        hover = [
            f"<b>{row['vessel_name']}</b><br>"
            f"Arrived: {row['arrived_at']}<br>"
            f"Duration: {row['duration_h']:.1f} h<br>"
            f"DWT: {row['dwt']:,.0f}"
            for _, row in sub.iterrows()
        ]
        fig.add_trace(go.Scatter(
            x=sub["arrived_at"],
            y=sub["vessel_type"],
            mode="markers",
            marker=dict(
                size=sizes.tolist(),
                color=VESSEL_TYPE_COLOURS.get(vtype, "#BDC3C7"),
                opacity=0.8,
            ),
            text=hover,
            hoverinfo="text",
            name=vtype,
        ))

    fig.update_layout(
        title="Individual vessel visits",
        xaxis_title="Arrival date",
        yaxis_title="Vessel type",
        template="plotly_dark",
    )
    return fig
