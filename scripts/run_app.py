#!/usr/bin/env python
"""
run_app.py – CLI entry point for the TankerWatch Dash application.

Usage:
  python scripts/run_app.py
  python scripts/run_app.py --host 127.0.0.1 --port 8080 --debug
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import click
import dash
import dash_bootstrap_components as dbc
import yaml

from tankerwatch.app.callbacks import register_callbacks
from tankerwatch.app.layout import create_layout
from tankerwatch.db import init_db, get_session_factory
from sqlalchemy import select
from tankerwatch.db import Port

_DEFAULT_CONFIG = Path(__file__).parent.parent / "config.yaml"


def _get_port_options(db_path: str) -> list[dict]:
    factory = get_session_factory(db_path)
    with factory() as session:
        ports = session.execute(select(Port)).scalars().all()
    return [{"label": p.name, "value": p.id} for p in ports]


@click.command()
@click.option("--host", default=None, help="Host to bind to (overrides config).")
@click.option("--port", default=None, type=int, help="Port to listen on (overrides config).")
@click.option("--debug", is_flag=True, default=False, help="Enable Dash debug mode.")
@click.option("--config", default=str(_DEFAULT_CONFIG), show_default=True, help="Path to config.yaml.")
def main(host: str | None, port: int | None, debug: bool, config: str) -> None:
    """Launch the TankerWatch Dash dashboard."""
    config_path = Path(config)
    with open(config_path) as fh:
        cfg = yaml.safe_load(fh)

    db_path = cfg["database"]["path"]
    init_db(db_path)

    app_cfg = cfg.get("app", {})
    _host = host or app_cfg.get("host", "0.0.0.0")
    _port = port or app_cfg.get("port", 8050)
    _debug = debug or app_cfg.get("debug", False)

    port_options = _get_port_options(db_path)

    app = dash.Dash(
        __name__,
        external_stylesheets=[dbc.themes.DARKLY],
        suppress_callback_exceptions=True,
    )
    app.layout = create_layout(port_options=port_options)
    register_callbacks(app)

    click.echo(f"Starting TankerWatch on http://{_host}:{_port}")
    app.run(host=_host, port=_port, debug=_debug)


if __name__ == "__main__":
    main()
