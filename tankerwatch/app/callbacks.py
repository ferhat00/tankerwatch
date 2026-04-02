"""
callbacks.py – All Dash callback definitions for TankerWatch.
"""

from __future__ import annotations

import io
import logging
from datetime import date, datetime, timezone

import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, callback, dcc, html
from sqlalchemy import select

import dash_bootstrap_components as dbc

from tankerwatch.app.analysis import (
    build_autocorrelation,
    build_heatmap,
    build_rolling_avg_chart,
)
from tankerwatch.app.map_view import build_vessel_map
from tankerwatch.app.port_ts import build_line_chart, build_stacked_bar, build_visit_scatter
from tankerwatch.db import Port, PortVisit, Position, Vessel, get_session_factory

logger = logging.getLogger(__name__)

_DB_PATH = "data/tankerwatch.db"


# ---------------------------------------------------------------------------
# Data access helpers
# ---------------------------------------------------------------------------

def _get_vessels_df(
    vessel_types: list[str] | None = None,
    min_dwt: int = 0,
    nav_statuses: list[str] | None = None,
) -> pd.DataFrame:
    """Return the most recent position for each vessel matching filters."""
    factory = get_session_factory(_DB_PATH)
    with factory() as session:
        stmt = (
            select(
                Vessel.imo,
                Vessel.name,
                Vessel.vessel_type,
                Vessel.dwt,
                Position.lat,
                Position.lon,
                Position.speed,
                Position.heading,
                Position.nav_status,
                Position.destination,
                Position.scraped_at,
            )
            .join(Position, Vessel.imo == Position.imo)
            .order_by(Position.scraped_at.desc())
        )
        rows = session.execute(stmt).fetchall()

    if not rows:
        return pd.DataFrame(columns=[
            "imo", "name", "vessel_type", "dwt", "lat", "lon",
            "speed", "heading", "nav_status", "destination", "scraped_at",
        ])

    df = pd.DataFrame(rows, columns=[
        "imo", "name", "vessel_type", "dwt", "lat", "lon",
        "speed", "heading", "nav_status", "destination", "scraped_at",
    ])

    # Keep only the latest position per vessel
    df = df.drop_duplicates(subset=["imo"], keep="first")

    # Filters
    if vessel_types:
        df = df[df["vessel_type"].isin(vessel_types)]
    if min_dwt:
        df = df[df["dwt"].fillna(0) >= min_dwt]
    if nav_statuses:
        df = df[
            df["nav_status"].str.lower().str.contains(
                "|".join(nav_statuses), na=False
            )
        ]

    return df


def _get_port_visits_df(
    port_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    vessel_types: list[str] | None = None,
) -> pd.DataFrame:
    factory = get_session_factory(_DB_PATH)
    with factory() as session:
        stmt = (
            select(
                PortVisit.imo,
                PortVisit.port_name,
                PortVisit.arrived_at,
                PortVisit.departed_at,
                Vessel.name.label("vessel_name"),
                Vessel.vessel_type,
                Vessel.dwt,
            )
            .join(Vessel, PortVisit.imo == Vessel.imo)
        )
        if port_id is not None:
            stmt = stmt.where(PortVisit.port_id == port_id)
        rows = session.execute(stmt).fetchall()

    if not rows:
        return pd.DataFrame(columns=[
            "imo", "port_name", "arrived_at", "departed_at",
            "vessel_name", "vessel_type", "dwt",
        ])

    df = pd.DataFrame(rows, columns=[
        "imo", "port_name", "arrived_at", "departed_at",
        "vessel_name", "vessel_type", "dwt",
    ])

    if start_date:
        df = df[pd.to_datetime(df["arrived_at"]) >= pd.to_datetime(start_date)]
    if end_date:
        df = df[pd.to_datetime(df["arrived_at"]) <= pd.to_datetime(end_date)]
    if vessel_types:
        df = df[df["vessel_type"].isin(vessel_types)]

    return df


def _get_port_options() -> list[dict]:
    factory = get_session_factory(_DB_PATH)
    with factory() as session:
        ports = session.execute(select(Port)).scalars().all()
    return [{"label": p.name, "value": p.id} for p in ports]


# ---------------------------------------------------------------------------
# Callback registration
# ---------------------------------------------------------------------------

def register_callbacks(app) -> None:  # noqa: ANN001
    """Register all Dash callbacks on *app*."""

    # ------------------------------------------------------------------
    # Populate port dropdowns on load
    # ------------------------------------------------------------------
    @app.callback(
        Output("port-selector", "options"),
        Output("ts-port-selector", "options"),
        Input("auto-refresh", "n_intervals"),
    )
    def update_port_options(_n):
        opts = _get_port_options()
        return opts, opts

    # ------------------------------------------------------------------
    # Tab 1 – Live Map
    # ------------------------------------------------------------------
    @app.callback(
        Output("vessel-map", "figure"),
        Input("map-refresh-btn", "n_clicks"),
        Input("auto-refresh", "n_intervals"),
        Input("map-vessel-type-filter", "value"),
        Input("map-dwt-slider", "value"),
        Input("map-nav-status-filter", "value"),
    )
    def update_map(_clicks, _intervals, vessel_types, min_dwt, nav_statuses):
        df = _get_vessels_df(vessel_types, min_dwt or 0, nav_statuses)
        return build_vessel_map(df)

    # ------------------------------------------------------------------
    # Tab 2 – Port Analysis KPIs
    # ------------------------------------------------------------------
    @app.callback(
        Output("port-kpi-cards", "children"),
        Input("port-selector", "value"),
        Input("port-date-range", "start_date"),
        Input("port-date-range", "end_date"),
        Input("port-vessel-type-filter", "value"),
    )
    def update_port_kpis(port_id, start_date, end_date, vessel_types):
        df = _get_port_visits_df(port_id, start_date, end_date, vessel_types)
        if df.empty:
            return [dbc.Col(dbc.Alert("No visit data for the selected filters.", color="info"), width=12)]

        total_visits = len(df)

        df["arrived_at"] = pd.to_datetime(df["arrived_at"])
        df["departed_at"] = pd.to_datetime(df["departed_at"])
        df["duration_h"] = (
            (df["departed_at"] - df["arrived_at"]).dt.total_seconds() / 3600
        ).clip(lower=0)
        avg_duration = df["duration_h"].mean()

        busiest_type = df["vessel_type"].value_counts().idxmax() if not df.empty else "N/A"
        longest_visit = df["duration_h"].max()

        cards = [
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H4(f"{total_visits:,}", className="card-title text-info"),
                html.P("Total visits", className="card-text"),
            ])), width=3),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H4(f"{avg_duration:.1f} h" if not pd.isna(avg_duration) else "N/A", className="card-title text-warning"),
                html.P("Avg visit duration", className="card-text"),
            ])), width=3),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H4(busiest_type, className="card-title text-success"),
                html.P("Busiest vessel type", className="card-text"),
            ])), width=3),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.H4(f"{longest_visit:.1f} h" if not pd.isna(longest_visit) else "N/A", className="card-title text-danger"),
                html.P("Longest visit", className="card-text"),
            ])), width=3),
        ]
        return cards

    # ------------------------------------------------------------------
    # Tab 2 – Charts A, B, C
    # ------------------------------------------------------------------
    @app.callback(
        Output("port-chart-a", "figure"),
        Output("port-chart-b", "figure"),
        Output("port-chart-c", "figure"),
        Input("port-selector", "value"),
        Input("port-date-range", "start_date"),
        Input("port-date-range", "end_date"),
        Input("port-vessel-type-filter", "value"),
    )
    def update_port_charts(port_id, start_date, end_date, vessel_types):
        df = _get_port_visits_df(port_id, start_date, end_date, vessel_types)
        return (
            build_stacked_bar(df),
            build_line_chart(df),
            build_visit_scatter(df),
        )

    # ------------------------------------------------------------------
    # Tab 3 – Charts D, E, F
    # ------------------------------------------------------------------
    @app.callback(
        Output("ts-chart-d", "figure"),
        Output("ts-chart-e", "figure"),
        Output("ts-chart-f", "figure"),
        Input("ts-port-selector", "value"),
        Input("ts-vessel-type-filter", "value"),
    )
    def update_ts_charts(port_id, vessel_types):
        df = _get_port_visits_df(port_id, vessel_types=vessel_types)
        return (
            build_rolling_avg_chart(df),
            build_heatmap(df),
            build_autocorrelation(df),
        )

    # ------------------------------------------------------------------
    # Tab 3 – Export CSV
    # ------------------------------------------------------------------
    @app.callback(
        Output("ts-download", "data"),
        Input("ts-export-btn", "n_clicks"),
        State("ts-port-selector", "value"),
        State("ts-vessel-type-filter", "value"),
        prevent_initial_call=True,
    )
    def export_csv(_n, port_id, vessel_types):
        df = _get_port_visits_df(port_id, vessel_types=vessel_types)
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return dcc.send_string(buf.getvalue(), filename=f"tankerwatch_export_{ts}.csv")
