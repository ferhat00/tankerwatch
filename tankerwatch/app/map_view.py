"""
map_view.py – Plotly Scattermapbox vessel map helpers.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

# Fixed colour palette per vessel type
VESSEL_TYPE_COLOURS: dict[str, str] = {
    "VLCC": "#E74C3C",
    "Suezmax": "#E67E22",
    "Aframax": "#F1C40F",
    "LR2": "#2ECC71",
    "LR1": "#2ECC71",
    "MR": "#3498DB",
    "Handysize": "#3498DB",
    "LNG": "#9B59B6",
    "LPG": "#1ABC9C",
    "Chemical": "#95A5A6",
    "Unknown": "#BDC3C7",
}

_DEFAULT_DWT = 50_000  # fallback for sizing when DWT is missing
_MIN_MARKER_SIZE = 5
_MAX_MARKER_SIZE = 20


def _scale_dwt(dwt: float | None) -> float:
    """Map DWT to a marker size in the range [_MIN, _MAX]."""
    if dwt is None or dwt <= 0:
        dwt = _DEFAULT_DWT
    # VLCCs ~300k DWT, Handysize ~25k DWT
    normalised = min(dwt / 320_000, 1.0)
    return _MIN_MARKER_SIZE + normalised * (_MAX_MARKER_SIZE - _MIN_MARKER_SIZE)


def build_vessel_map(
    df: pd.DataFrame,
    mapbox_style: str = "open-street-map",
) -> go.Figure:
    """
    Build a Scattermapbox figure from a vessel DataFrame.

    Expected columns: imo, name, vessel_type, lat, lon, speed,
                      destination, dwt, nav_status, scraped_at
    """
    fig = go.Figure()

    vessel_types = df["vessel_type"].unique() if not df.empty else []

    for vtype in sorted(vessel_types):
        sub = df[df["vessel_type"] == vtype]
        colour = VESSEL_TYPE_COLOURS.get(vtype, "#BDC3C7")
        sizes = sub["dwt"].apply(_scale_dwt).tolist()

        hover_texts = []
        for _, row in sub.iterrows():
            speed_str = f"{row['speed']:.1f} kn" if pd.notna(row.get("speed")) else "N/A"
            dest_str = row.get("destination") or "N/A"
            upd_str = str(row.get("scraped_at", ""))[:19]
            hover_texts.append(
                f"<b>{row['name']}</b><br>"
                f"Type: {row['vessel_type']}<br>"
                f"Speed: {speed_str}<br>"
                f"Destination: {dest_str}<br>"
                f"Last updated: {upd_str}"
            )

        fig.add_trace(go.Scattermapbox(
            lat=sub["lat"].tolist(),
            lon=sub["lon"].tolist(),
            mode="markers",
            marker=dict(
                size=sizes,
                color=colour,
                opacity=0.8,
            ),
            text=hover_texts,
            hoverinfo="text",
            name=vtype,
        ))

    fig.update_layout(
        mapbox=dict(
            style=mapbox_style,
            zoom=2,
            center=dict(lat=20, lon=20),
        ),
        margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(
            bgcolor="rgba(30,30,30,0.7)",
            font=dict(color="white"),
        ),
        paper_bgcolor="#1a1a2e",
        plot_bgcolor="#1a1a2e",
        uirevision="vessel-map",  # preserve zoom/pan across updates
    )
    return fig
