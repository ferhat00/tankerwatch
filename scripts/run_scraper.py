#!/usr/bin/env python
"""
run_scraper.py – CLI entry point for the TankerWatch scraper.

Usage:
  python scripts/run_scraper.py --once           # single scrape cycle
  python scripts/run_scraper.py --schedule       # run on configured interval
  python scripts/run_scraper.py --once --debug-network  # print intercepted URLs
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow importing the tankerwatch package from the repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

import click
import yaml

from tankerwatch.db import init_db
from tankerwatch.scheduler import run_scrape_job, start_scheduler

_DEFAULT_CONFIG = Path(__file__).parent.parent / "config.yaml"


@click.command()
@click.option("--once", is_flag=True, default=False, help="Run a single scrape cycle then exit.")
@click.option("--schedule", is_flag=True, default=False, help="Run on the configured interval (blocking).")
@click.option("--debug-network", is_flag=True, default=False, help="Print all intercepted URLs.")
@click.option("--config", default=str(_DEFAULT_CONFIG), show_default=True, help="Path to config.yaml.")
def main(once: bool, schedule: bool, debug_network: bool, config: str) -> None:
    """TankerWatch scraper CLI."""
    if not once and not schedule:
        click.echo("Specify --once or --schedule.  Use --help for usage.")
        raise SystemExit(1)

    config_path = Path(config)
    with open(config_path) as fh:
        cfg = yaml.safe_load(fh)

    db_path = cfg["database"]["path"]
    init_db(db_path)

    if once:
        run_scrape_job(config=cfg, debug_network=debug_network)
    else:
        start_scheduler(config=cfg, debug_network=debug_network)


if __name__ == "__main__":
    main()
