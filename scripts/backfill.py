#!/usr/bin/env python
"""
backfill.py – Replay all cached raw JSON files through the parser and into the DB.

Useful when the schema or parser logic changes.

Usage:
  python scripts/backfill.py
  python scripts/backfill.py --raw-dir data/raw --db data/tankerwatch.db
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import click
from rich.console import Console
from rich.progress import track

from tankerwatch.db import init_db, save_vessels
from tankerwatch.parser import parse_vessels

console = Console()


@click.command()
@click.option("--raw-dir", default="data/raw", show_default=True, help="Directory with cached JSON files.")
@click.option("--db", default="data/tankerwatch.db", show_default=True, help="SQLite database path.")
def main(raw_dir: str, db: str) -> None:
    """Backfill the database from cached raw JSON files."""
    raw_path = Path(raw_dir)
    if not raw_path.exists():
        console.print(f"[red]Raw directory not found:[/red] {raw_dir}")
        raise SystemExit(1)

    files = sorted(raw_path.glob("*.json"))
    if not files:
        console.print(f"[yellow]No JSON files in {raw_dir}[/yellow]")
        return

    console.print(f"[bold]Backfilling from {len(files)} cached files…[/bold]")
    init_db(db)

    total_vessels = 0
    total_positions = 0

    for f in track(files, description="Processing…"):
        try:
            raw = json.loads(f.read_text())
            if isinstance(raw, dict):
                raw = [raw]
            records = parse_vessels(raw)
            stats = save_vessels(records, db)
            total_vessels += stats["vessels_upserted"]
            total_positions += stats["positions_inserted"]
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            console.print(f"[red]Error processing {f.name}:[/red] {exc}")

    console.print(
        f"[bold green]Backfill complete.[/bold green] "
        f"Vessels upserted: {total_vessels}, positions inserted: {total_positions}"
    )


if __name__ == "__main__":
    main()
