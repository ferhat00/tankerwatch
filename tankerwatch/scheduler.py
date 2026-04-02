"""
scheduler.py – APScheduler job that periodically scrapes TankerMap and
persists the results to the database.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from rich.console import Console

from tankerwatch.db import init_db, infer_port_visits, save_vessels
from tankerwatch.parser import parse_vessels
from tankerwatch.scraper import scrape

console = Console()
logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def _load_config(config_path: Path = _DEFAULT_CONFIG_PATH) -> dict:
    with open(config_path) as fh:
        return yaml.safe_load(fh)


def run_scrape_job(config: dict | None = None, debug_network: bool = False) -> None:
    """Single scrape cycle: fetch → parse → persist → infer port visits."""
    if config is None:
        config = _load_config()

    db_path = config["database"]["path"]
    prox_km = config["ports"]["proximity_km"]
    min_readings = config["ports"]["min_stationary_readings"]
    stat_speed = config["ports"]["stationary_speed_knots"]

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    console.rule(f"[bold blue]Scrape cycle[/bold blue] {ts}")

    try:
        raw = scrape(config, debug_network=debug_network)
        records = parse_vessels(raw)
        stats = save_vessels(records, db_path)

        console.print(
            f"  [green]✓[/green] vessels upserted: [bold]{stats['vessels_upserted']}[/bold]  "
            f"positions: [bold]{stats['positions_inserted']}[/bold]"
        )

        new_visits = infer_port_visits(
            db_path=db_path,
            proximity_km=prox_km,
            min_stationary_readings=min_readings,
            stationary_speed_knots=stat_speed,
        )
        if new_visits:
            console.print(f"  [cyan]New port visits inferred:[/cyan] {new_visits}")

    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:  # noqa: BLE001
        logger.exception("Scrape job failed")
        console.print_exception()


def start_scheduler(config: dict | None = None, debug_network: bool = False) -> None:
    """Start the blocking APScheduler loop."""
    if config is None:
        config = _load_config()

    db_path = config["database"]["path"]
    interval_minutes = config["scraper"]["interval_minutes"]

    console.print(
        f"[bold]TankerWatch scheduler[/bold] starting – "
        f"interval: [cyan]{interval_minutes}[/cyan] minutes"
    )
    init_db(db_path)

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        run_scrape_job,
        trigger=IntervalTrigger(minutes=interval_minutes),
        kwargs={"config": config, "debug_network": debug_network},
        id="scrape",
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc),  # run immediately on start
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        console.print("[yellow]Scheduler stopped.[/yellow]")
