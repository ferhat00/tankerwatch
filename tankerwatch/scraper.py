"""
scraper.py – TankerMap HTTP scraper.

Strategy:
1. Try plain httpx GET to known API endpoints.
2. If that fails or returns no data, fall back to Playwright (headless Chromium)
   which intercepts XHR/fetch responses matching vessel-data URL patterns.

Raw JSON responses are cached to ``data/raw/`` as timestamped files so that
no data is ever lost if the parser changes later.
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml
from rich.console import Console

console = Console()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def _load_config(config_path: Path = _DEFAULT_CONFIG_PATH) -> dict:
    with open(config_path) as fh:
        return yaml.safe_load(fh)


# ---------------------------------------------------------------------------
# User-Agent pool
# ---------------------------------------------------------------------------

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

# ---------------------------------------------------------------------------
# Known TankerMap API endpoint candidates
# ---------------------------------------------------------------------------

TANKERMAP_BASE = "https://tankermap.com"
ENDPOINT_CANDIDATES = [
    "/api/vessels",
    "/api/positions",
    "/api/v1/vessels",
    "/api/v2/vessels",
    "/data/vessels.json",
    "/data/positions.json",
    "/vessels",
    "/positions",
]

# URL patterns used to filter intercepted XHR traffic in Playwright mode
INTERCEPT_PATTERNS = [
    "*vessels*",
    "*positions*",
    "*ais*",
    "*tankers*",
    "*fleet*",
]


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _ensure_raw_dir(raw_dir: str) -> Path:
    p = Path(raw_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cache_raw(data: Any, tag: str, raw_dir: str) -> Path:
    """Write *data* as a timestamped JSON file and return its path."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = _ensure_raw_dir(raw_dir) / f"{tag}_{ts}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    logger.debug("Cached raw response → %s", out)
    return out


# ---------------------------------------------------------------------------
# httpx scraper
# ---------------------------------------------------------------------------

def _random_headers() -> dict[str, str]:
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": TANKERMAP_BASE + "/",
        "Origin": TANKERMAP_BASE,
    }


def _fetch_with_backoff(
    client: httpx.Client,
    url: str,
    max_retries: int = 3,
    min_delay: float = 1.0,
) -> httpx.Response | None:
    delay = min_delay
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.get(url, headers=_random_headers(), timeout=30)
            if resp.status_code == 429:
                logger.warning("Rate-limited (429) on %s; waiting %.1fs", url, delay)
                time.sleep(delay)
                delay *= 2
                continue
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as exc:
            logger.warning("HTTP %s on %s (attempt %d)", exc.response.status_code, url, attempt)
        except httpx.RequestError as exc:
            logger.warning("Request error on %s (attempt %d): %s", url, attempt, exc)
        if attempt < max_retries:
            time.sleep(delay)
            delay *= 2
    return None


def scrape_httpx(
    config: dict | None = None,
    debug_network: bool = False,
) -> list[dict]:
    """Try each known endpoint with httpx.  Returns a list of raw JSON objects."""
    if config is None:
        config = _load_config()

    raw_dir = config["scraper"]["raw_cache_dir"]
    max_retries = config["scraper"]["max_retries"]
    min_delay = float(config["scraper"]["min_delay_seconds"])

    results: list[dict] = []

    with httpx.Client(follow_redirects=True) as client:
        # First, fetch the homepage and look for embedded API hints
        home_resp = _fetch_with_backoff(client, TANKERMAP_BASE, max_retries, 1.0)
        if home_resp is not None and debug_network:
            console.print(f"[cyan]Homepage status:[/cyan] {home_resp.status_code}")
            _cache_raw({"html": home_resp.text[:4096]}, "homepage", raw_dir)

        for endpoint in ENDPOINT_CANDIDATES:
            url = TANKERMAP_BASE + endpoint
            if debug_network:
                console.print(f"[yellow]Trying:[/yellow] {url}")
            resp = _fetch_with_backoff(client, url, max_retries, 1.0)
            if resp is None:
                continue
            ct = resp.headers.get("content-type", "")
            if "json" in ct:
                try:
                    data = resp.json()
                    _cache_raw(data, "httpx_vessels", raw_dir)
                    if debug_network:
                        console.print(f"[green]Got JSON from {url}[/green]")
                    if isinstance(data, list):
                        results.extend(data)
                    elif isinstance(data, dict):
                        # Try common keys
                        for key in ("vessels", "data", "features", "results"):
                            if key in data and isinstance(data[key], list):
                                results.extend(data[key])
                                break
                        else:
                            results.append(data)
                except (json.JSONDecodeError, ValueError) as exc:
                    logger.debug("Failed to parse JSON from %s: %s", url, exc)
            elif debug_network:
                console.print(f"[dim]Non-JSON response ({ct}) from {url}[/dim]")

    return results


# ---------------------------------------------------------------------------
# Playwright fallback scraper
# ---------------------------------------------------------------------------

def scrape_playwright(
    config: dict | None = None,
    debug_network: bool = False,
) -> list[dict]:
    """
    Launch a headless Chromium browser, navigate to TankerMap, and intercept
    all JSON responses matching vessel/position URL patterns.
    """
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError:
        logger.error("playwright is not installed – run: playwright install chromium")
        return []

    if config is None:
        config = _load_config()

    raw_dir = config["scraper"]["raw_cache_dir"]
    captured: list[dict] = []
    captured_urls: list[str] = []

    def _matches_pattern(url: str) -> bool:
        import fnmatch  # noqa: PLC0415
        low = url.lower()
        for pat in INTERCEPT_PATTERNS:
            if fnmatch.fnmatch(low, pat):
                return True
        return False

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=random.choice(_USER_AGENTS),
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        def on_response(response):  # noqa: ANN001
            try:
                url = response.url
                if not _matches_pattern(url):
                    return
                ct = response.headers.get("content-type", "")
                if "json" not in ct:
                    return
                if debug_network:
                    console.print(f"[green]Intercepted:[/green] {url}")
                captured_urls.append(url)
                data = response.json()
                _cache_raw(data, "playwright_vessels", raw_dir)
                if isinstance(data, list):
                    captured.extend(data)
                elif isinstance(data, dict):
                    for key in ("vessels", "data", "features", "results"):
                        if key in data and isinstance(data[key], list):
                            captured.extend(data[key])
                            break
                    else:
                        captured.append(data)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Error processing response from %s: %s", url, exc)

        page.on("response", on_response)

        try:
            page.goto(TANKERMAP_BASE, wait_until="networkidle", timeout=60_000)
            # Give the page a couple of seconds for lazy XHR calls
            page.wait_for_timeout(3000)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Playwright navigation error: %s", exc)
        finally:
            context.close()
            browser.close()

    if debug_network:
        console.print(f"[cyan]Intercepted {len(captured_urls)} matching URLs[/cyan]")
        for u in captured_urls:
            console.print(f"  {u}")

    return captured


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def scrape(
    config: dict | None = None,
    debug_network: bool = False,
) -> list[dict]:
    """
    Scrape vessel data from TankerMap.

    1. Try httpx (fast, no browser needed).
    2. If no results and use_playwright_fallback is True, fall back to Playwright.

    Returns a list of raw vessel dicts.
    """
    if config is None:
        config = _load_config()

    use_pw = config["scraper"].get("use_playwright_fallback", True)

    console.print("[bold blue]TankerWatch[/bold blue] – starting scrape (httpx)…")
    results = scrape_httpx(config, debug_network)

    if not results and use_pw:
        console.print("[yellow]httpx found no data – trying Playwright fallback…[/yellow]")
        results = scrape_playwright(config, debug_network)

    console.print(f"[bold green]Scrape complete:[/bold green] {len(results)} raw records")
    return results
