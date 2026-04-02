"""
layout.py – Dash layout definition for TankerWatch.

Three tabs:
  Tab 1 – Live Map
  Tab 2 – Port Analysis
  Tab 3 – Time Series Analysis
"""

from __future__ import annotations

from datetime import date, timedelta

import dash_bootstrap_components as dbc
from dash import dcc, html

from tankerwatch.app.map_view import VESSEL_TYPE_COLOURS

# ---------------------------------------------------------------------------
# Reusable component helpers
# ---------------------------------------------------------------------------

ALL_VESSEL_TYPES = list(VESSEL_TYPE_COLOURS.keys())

NAV_STATUS_OPTIONS = [
    {"label": "Underway", "value": "underway"},
    {"label": "Anchored", "value": "anchored"},
    {"label": "Moored", "value": "moored"},
]


def _vessel_type_checklist(component_id: str, value: list[str] | None = None) -> dbc.Card:
    return dbc.Card(
        dbc.CardBody([
            html.Label("Vessel Type", className="fw-bold"),
            dcc.Checklist(
                id=component_id,
                options=[{"label": vt, "value": vt} for vt in ALL_VESSEL_TYPES],
                value=value or ALL_VESSEL_TYPES,
                labelStyle={"display": "block"},
                inputStyle={"marginRight": "6px"},
            ),
        ]),
        className="mb-2",
    )


# ---------------------------------------------------------------------------
# Tab 1 – Live Map
# ---------------------------------------------------------------------------

_tab1 = dbc.Tab(
    label="🗺  Live Map",
    tab_id="tab-map",
    children=[
        dbc.Row([
            # Sidebar controls
            dbc.Col([
                _vessel_type_checklist("map-vessel-type-filter"),
                dbc.Card(
                    dbc.CardBody([
                        html.Label("Min DWT", className="fw-bold"),
                        dcc.Slider(
                            id="map-dwt-slider",
                            min=0,
                            max=320_000,
                            step=10_000,
                            value=0,
                            marks={
                                0: "0",
                                100_000: "100k",
                                200_000: "200k",
                                320_000: "320k",
                            },
                            tooltip={"placement": "bottom", "always_visible": False},
                        ),
                    ]),
                    className="mb-2",
                ),
                dbc.Card(
                    dbc.CardBody([
                        html.Label("Nav Status", className="fw-bold"),
                        dcc.Checklist(
                            id="map-nav-status-filter",
                            options=NAV_STATUS_OPTIONS,
                            value=["underway", "anchored", "moored"],
                            labelStyle={"display": "block"},
                            inputStyle={"marginRight": "6px"},
                        ),
                    ]),
                    className="mb-2",
                ),
                dbc.Card(
                    dbc.CardBody([
                        html.H6("Legend", className="fw-bold"),
                        *[
                            html.Div([
                                html.Span(
                                    "●",
                                    style={"color": colour, "fontSize": "20px", "marginRight": "8px"},
                                ),
                                html.Span(vtype),
                            ])
                            for vtype, colour in VESSEL_TYPE_COLOURS.items()
                            if vtype != "Unknown"
                        ],
                    ]),
                    className="mb-2",
                ),
                dbc.Button(
                    "Refresh Map",
                    id="map-refresh-btn",
                    color="primary",
                    className="w-100 mt-1",
                ),
            ], width=2),
            # Map
            dbc.Col([
                dcc.Loading(
                    dcc.Graph(
                        id="vessel-map",
                        style={"height": "80vh"},
                        config={"scrollZoom": True},
                    ),
                ),
            ], width=10),
        ], className="mt-2"),
    ],
)


# ---------------------------------------------------------------------------
# Tab 2 – Port Analysis
# ---------------------------------------------------------------------------

_tab2 = dbc.Tab(
    label="⚓ Port Analysis",
    tab_id="tab-port",
    children=[
        dbc.Row([
            dbc.Col([
                dbc.Card(dbc.CardBody([
                    html.Label("Select Port", className="fw-bold"),
                    dcc.Dropdown(id="port-selector", placeholder="Choose a port…", clearable=False),
                ]), className="mb-2"),
                dbc.Card(dbc.CardBody([
                    html.Label("Date Range", className="fw-bold"),
                    dcc.DatePickerRange(
                        id="port-date-range",
                        start_date=(date.today() - timedelta(days=90)).isoformat(),
                        end_date=date.today().isoformat(),
                        display_format="YYYY-MM-DD",
                        className="w-100",
                    ),
                ]), className="mb-2"),
                _vessel_type_checklist("port-vessel-type-filter"),
            ], width=3),
            dbc.Col([
                # KPI cards
                dbc.Row(id="port-kpi-cards", className="mb-2"),
                dcc.Loading(dcc.Graph(id="port-chart-a")),
                dcc.Loading(dcc.Graph(id="port-chart-b")),
                dcc.Loading(dcc.Graph(id="port-chart-c")),
            ], width=9),
        ], className="mt-2"),
    ],
)


# ---------------------------------------------------------------------------
# Tab 3 – Time Series Analysis
# ---------------------------------------------------------------------------

_tab3 = dbc.Tab(
    label="📈 Time Series Analysis",
    tab_id="tab-ts",
    children=[
        dbc.Row([
            dbc.Col([
                dbc.Card(dbc.CardBody([
                    html.Label("Select Port", className="fw-bold"),
                    dcc.Dropdown(id="ts-port-selector", placeholder="All ports", clearable=True),
                ]), className="mb-2"),
                _vessel_type_checklist("ts-vessel-type-filter"),
                dbc.Button(
                    "Export CSV",
                    id="ts-export-btn",
                    color="secondary",
                    className="w-100 mt-1",
                ),
                dcc.Download(id="ts-download"),
            ], width=3),
            dbc.Col([
                dcc.Loading(dcc.Graph(id="ts-chart-d")),
                dcc.Loading(dcc.Graph(id="ts-chart-e")),
                dcc.Loading(dcc.Graph(id="ts-chart-f")),
            ], width=9),
        ], className="mt-2"),
    ],
)


# ---------------------------------------------------------------------------
# App layout
# ---------------------------------------------------------------------------

def create_layout(port_options: list[dict] | None = None) -> html.Div:
    """Return the top-level Dash layout."""
    if port_options is None:
        port_options = []

    return html.Div([
        # Interval component for auto-refresh
        dcc.Interval(id="auto-refresh", interval=5 * 60 * 1000, n_intervals=0),  # every 5 min

        dbc.NavbarSimple(
            brand="🛢 TankerWatch",
            brand_href="#",
            color="dark",
            dark=True,
            className="mb-3",
        ),

        dbc.Container(
            dbc.Tabs(
                [_tab1, _tab2, _tab3],
                id="main-tabs",
                active_tab="tab-map",
            ),
            fluid=True,
        ),
    ])
