"""
parser.py – parse raw JSON dicts from TankerMap into typed dataclasses.

The exact JSON shape from TankerMap is not publicly documented; this module
handles several plausible formats and normalises them into common dataclasses.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Vessel type normalisation
# ---------------------------------------------------------------------------

_TYPE_MAP: dict[str, str] = {
    # VLCC
    "vlcc": "VLCC",
    "very large crude carrier": "VLCC",
    # Suezmax
    "suezmax": "Suezmax",
    # Aframax
    "aframax": "Aframax",
    # LR2
    "lr2": "LR2",
    "long range 2": "LR2",
    # LR1
    "lr1": "LR1",
    "long range 1": "LR1",
    # MR
    "mr": "MR",
    "medium range": "MR",
    # Handysize
    "handysize": "Handysize",
    "handymax": "Handysize",
    # LNG
    "lng": "LNG",
    "lng carrier": "LNG",
    "liquefied natural gas tanker": "LNG",
    # LPG
    "lpg": "LPG",
    "lpg carrier": "LPG",
    "liquefied petroleum gas tanker": "LPG",
    # Chemical
    "chemical": "Chemical",
    "chemical tanker": "Chemical",
    "products tanker": "Chemical",
    "oil products tanker": "Chemical",
    "refined oil products": "Chemical",
}


def normalise_vessel_type(raw: str | None) -> str:
    if not raw:
        return "Unknown"
    key = raw.strip().lower()
    return _TYPE_MAP.get(key, raw.strip())


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class VesselRecord:
    imo: str
    mmsi: str
    name: str
    vessel_type: str
    vessel_type_raw: str
    dwt: int | None
    built_year: int | None
    flag: str | None
    # position
    lat: float | None
    lon: float | None
    speed: float | None
    heading: int | None
    nav_status: str | None
    destination: str | None
    eta: datetime | None
    draught: float | None


def _safe_float(val: Any) -> float | None:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _safe_int(val: Any) -> int | None:
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _parse_dt(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(val, tz=timezone.utc)
        except (OSError, OverflowError):
            return None
    if isinstance(val, str):
        for fmt in (
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(val, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


# ---------------------------------------------------------------------------
# Key aliases: TankerMap may use different field names
# ---------------------------------------------------------------------------

_IMO_KEYS = ("imo", "imo_number", "IMO", "imoNumber")
_MMSI_KEYS = ("mmsi", "MMSI", "mmsiNumber")
_NAME_KEYS = ("name", "vessel_name", "shipname", "ship_name", "vesselName")
_TYPE_KEYS = ("vessel_type", "type", "shiptype", "ship_type", "vesselType", "tanker_type")
_DWT_KEYS = ("dwt", "DWT", "deadweight")
_BUILT_KEYS = ("built_year", "built", "year_built", "yearBuilt", "year")
_FLAG_KEYS = ("flag", "flag_code", "flagCode", "country")
_LAT_KEYS = ("lat", "latitude", "LAT")
_LON_KEYS = ("lon", "lng", "longitude", "LON", "LNG")
_SPEED_KEYS = ("speed", "sog", "SOG", "speed_over_ground")
_HEADING_KEYS = ("heading", "cog", "COG", "course")
_NAV_STATUS_KEYS = ("nav_status", "navStatus", "navigation_status", "status")
_DEST_KEYS = ("destination", "dest", "DEST")
_ETA_KEYS = ("eta", "ETA")
_DRAUGHT_KEYS = ("draught", "draft", "DRAUGHT")


def _get(d: dict, keys: tuple[str, ...], default: Any = None) -> Any:
    for k in keys:
        if k in d:
            return d[k]
    return default


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_vessel(raw: dict[str, Any]) -> VesselRecord | None:
    """
    Parse a single raw vessel dict into a VesselRecord.
    Returns None if the minimum required fields (IMO or MMSI) are missing.
    """
    imo = str(_get(raw, _IMO_KEYS, "") or "").strip()
    mmsi = str(_get(raw, _MMSI_KEYS, "") or "").strip()

    if not imo and not mmsi:
        logger.debug("Skipping record with no IMO/MMSI: %s", raw)
        return None

    if not imo:
        imo = f"MMSI-{mmsi}"

    name = str(_get(raw, _NAME_KEYS, "") or "").strip() or "Unknown"
    vessel_type_raw = str(_get(raw, _TYPE_KEYS, "") or "").strip()
    vessel_type = normalise_vessel_type(vessel_type_raw)

    return VesselRecord(
        imo=imo,
        mmsi=mmsi,
        name=name,
        vessel_type=vessel_type,
        vessel_type_raw=vessel_type_raw,
        dwt=_safe_int(_get(raw, _DWT_KEYS)),
        built_year=_safe_int(_get(raw, _BUILT_KEYS)),
        flag=str(_get(raw, _FLAG_KEYS, "") or "").strip() or None,
        lat=_safe_float(_get(raw, _LAT_KEYS)),
        lon=_safe_float(_get(raw, _LON_KEYS)),
        speed=_safe_float(_get(raw, _SPEED_KEYS)),
        heading=_safe_int(_get(raw, _HEADING_KEYS)),
        nav_status=str(_get(raw, _NAV_STATUS_KEYS, "") or "").strip() or None,
        destination=str(_get(raw, _DEST_KEYS, "") or "").strip() or None,
        eta=_parse_dt(_get(raw, _ETA_KEYS)),
        draught=_safe_float(_get(raw, _DRAUGHT_KEYS)),
    )


def parse_vessels(raw_list: list[dict[str, Any]]) -> list[VesselRecord]:
    """Parse a list of raw dicts into VesselRecords, skipping invalid entries."""
    records: list[VesselRecord] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        record = parse_vessel(item)
        if record is not None:
            records.append(record)
    logger.info("Parsed %d/%d vessel records", len(records), len(raw_list))
    return records
