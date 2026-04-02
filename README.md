# TankerWatch 🛢

A Python tool that scrapes vessel data from [TankerMap](https://tankermap.com),
stores historical snapshots in a local SQLite database, and serves an interactive
Dash dashboard for analysis.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        TankerWatch                          │
│                                                             │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌────────┐  │
│  │ Scraper  │──▶│  Parser  │──▶│  DB      │◀──│ Sched. │  │
│  │(httpx /  │   │(dataclass│   │(SQLite / │   │(APSched│  │
│  │playwright│   │  typed)  │   │ SQLAlch.)│   │  uler) │  │
│  └──────────┘   └──────────┘   └──────────┘   └────────┘  │
│                                      │                      │
│                              ┌───────▼───────┐             │
│                              │   Dash App    │             │
│                              │  ┌──────────┐ │             │
│                              │  │ Live Map │ │             │
│                              │  │ Port TS  │ │             │
│                              │  │ Analysis │ │             │
│                              │  └──────────┘ │             │
│                              └───────────────┘             │
└─────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

- Python 3.11+
- `pip install -r requirements.txt`
- `playwright install chromium` (for the JavaScript fallback scraper)

---

## Quickstart

```bash
# 1. Clone and install
git clone https://github.com/ferhat00/tankerwatch.git
cd tankerwatch
pip install -r requirements.txt
playwright install chromium

# 2. Copy the environment file (optional)
cp .env.example .env

# 3. Run a single scrape cycle to seed the database
python scripts/run_scraper.py --once

# 4. Launch the dashboard
python scripts/run_app.py

# 5. Open in your browser
open http://localhost:8050
```

Or use the Makefile:

```bash
make install   # pip install + playwright install
make scrape    # start the scheduled scraper
make app       # launch the dashboard
make test      # run the test suite
```

---

## Screenshots

_Dashboard screenshots will be added here once the scraper has accumulated
sufficient data._

| Tab | Description |
|-----|-------------|
| 🗺 Live Map | Plotly Scattermapbox with vessels sized by DWT, coloured by type |
| ⚓ Port Analysis | Weekly visit bar/line charts + individual visit scatter |
| 📈 Time Series | Rolling averages, heatmap, autocorrelation, anomaly detection |

---

## How Scraping Works

TankerMap is a Leaflet-based web app that fetches vessel positions via XHR/fetch
calls.  TankerWatch uses two complementary strategies:

1. **httpx (fast)** – tries a list of common REST endpoint patterns
   (`/api/vessels`, `/data/vessels.json`, etc.) directly.
2. **Playwright fallback (reliable)** – if httpx returns no data, launches a
   headless Chromium browser, navigates to TankerMap, and intercepts all JSON
   responses whose URL matches `*vessels*`, `*positions*`, `*ais*`, etc.

Raw JSON payloads are always cached to `data/raw/` as timestamped files so
that you can re-parse them later if the schema changes (use `scripts/backfill.py`).

> **Rate-limit policy**: The scraper waits a configurable minimum of 60 seconds
> between requests (default: scrape every 15 minutes) and uses exponential
> back-off on HTTP 429 responses.  Please be respectful of TankerMap's servers.

### Debug mode

```bash
python scripts/run_scraper.py --once --debug-network
```

Prints every intercepted URL so you can identify new API endpoints if the site
changes.

---

## Extending with Paid AIS APIs

The `tankerwatch/scraper.py` module exposes a single `scrape()` function that
returns a `list[dict]`.  Replacing the underlying data source is straightforward:

```python
# tankerwatch/scraper_datalastic.py (example)
import httpx

def scrape(config=None, debug_network=False):
    api_key = os.environ["DATALASTIC_API_KEY"]
    resp = httpx.get(
        "https://api.datalastic.com/api/v0/vessel_find",
        params={"api-key": api_key, "type": "tanker"},
    )
    return resp.json().get("data", [])
```

Then in `scheduler.py` replace:

```python
from tankerwatch.scraper import scrape
```

with your new module.  The `parser.py` key-alias system handles different field
names automatically.

---

## Configuration Reference

| Key | Default | Description |
|-----|---------|-------------|
| `scraper.interval_minutes` | `15` | How often to scrape |
| `scraper.min_delay_seconds` | `60` | Minimum delay between HTTP requests |
| `scraper.max_retries` | `3` | Retries per URL before giving up |
| `scraper.use_playwright_fallback` | `true` | Enable headless-browser fallback |
| `scraper.raw_cache_dir` | `data/raw` | Where to cache raw JSON files |
| `database.path` | `data/tankerwatch.db` | SQLite database file path |
| `app.host` | `0.0.0.0` | Dash server host |
| `app.port` | `8050` | Dash server port |
| `app.debug` | `false` | Enable Dash debug mode |
| `app.mapbox_style` | `open-street-map` | Mapbox tile style (no token needed) |
| `ports.proximity_km` | `10` | Radius for port matching |
| `ports.min_stationary_readings` | `3` | Min slow-speed readings to open a visit |
| `ports.stationary_speed_knots` | `0.5` | Speed threshold for "stationary" |

---

## Repo Structure

```
tankerwatch/
├── README.md
├── requirements.txt
├── .env.example
├── config.yaml
├── Makefile
├── alembic.ini
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 0001_initial_schema.py
├── tankerwatch/
│   ├── __init__.py
│   ├── scraper.py
│   ├── parser.py
│   ├── db.py
│   ├── scheduler.py
│   └── app/
│       ├── __init__.py
│       ├── layout.py
│       ├── callbacks.py
│       ├── map_view.py
│       ├── port_ts.py
│       └── analysis.py
├── scripts/
│   ├── run_scraper.py
│   ├── run_app.py
│   └── backfill.py
└── tests/
    ├── test_parser.py
    ├── test_db.py
    └── fixtures/
        └── sample_response.json
```

---

## License

MIT – see [LICENSE](LICENSE).
