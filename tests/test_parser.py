"""
test_parser.py – Unit tests for tankerwatch.parser.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tankerwatch.parser import (
    VesselRecord,
    normalise_vessel_type,
    parse_vessel,
    parse_vessels,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def sample_raw() -> list[dict]:
    return json.loads((FIXTURES_DIR / "sample_response.json").read_text())


# ---------------------------------------------------------------------------
# normalise_vessel_type
# ---------------------------------------------------------------------------

class TestNormaliseVesselType:
    def test_vlcc(self):
        assert normalise_vessel_type("vlcc") == "VLCC"
        assert normalise_vessel_type("VLCC") == "VLCC"

    def test_lng_carrier(self):
        assert normalise_vessel_type("LNG carrier") == "LNG"
        assert normalise_vessel_type("lng") == "LNG"
        assert normalise_vessel_type("liquefied natural gas tanker") == "LNG"

    def test_aframax(self):
        assert normalise_vessel_type("aframax") == "Aframax"

    def test_unknown(self):
        assert normalise_vessel_type("") == "Unknown"
        assert normalise_vessel_type(None) == "Unknown"

    def test_preserves_unknown_raw(self):
        result = normalise_vessel_type("Panamax Tanker")
        assert result == "Panamax Tanker"  # not in map → returned as-is


# ---------------------------------------------------------------------------
# parse_vessel
# ---------------------------------------------------------------------------

class TestParseVessel:
    def test_full_record(self):
        raw = {
            "imo": "9234567",
            "mmsi": "123456789",
            "name": "PACIFIC GLORY",
            "vessel_type": "VLCC",
            "dwt": 298000,
            "built_year": 2005,
            "flag": "Panama",
            "lat": 26.64,
            "lon": 50.16,
            "speed": 0.1,
            "heading": 180,
            "nav_status": "moored",
            "destination": "FUJAIRAH",
        }
        record = parse_vessel(raw)
        assert isinstance(record, VesselRecord)
        assert record.imo == "9234567"
        assert record.name == "PACIFIC GLORY"
        assert record.vessel_type == "VLCC"
        assert record.dwt == 298000
        assert record.lat == pytest.approx(26.64)
        assert record.lon == pytest.approx(50.16)
        assert record.speed == pytest.approx(0.1)

    def test_no_imo_uses_mmsi(self):
        raw = {"mmsi": "999888777", "name": "TEST"}
        record = parse_vessel(raw)
        assert record is not None
        assert record.imo == "MMSI-999888777"

    def test_missing_imo_and_mmsi_returns_none(self):
        raw = {"name": "Mystery Vessel", "note": "no identifiers"}
        result = parse_vessel(raw)
        assert result is None

    def test_vessel_type_normalised(self):
        raw = {"imo": "1111111", "vessel_type": "aframax"}
        record = parse_vessel(raw)
        assert record.vessel_type == "Aframax"
        assert record.vessel_type_raw == "aframax"

    def test_numeric_eta_parsed(self):
        import datetime
        raw = {"imo": "2222222", "eta": 1714550400}  # 2024-05-01 UTC
        record = parse_vessel(raw)
        assert record is not None
        assert isinstance(record.eta, datetime.datetime)

    def test_string_eta_parsed(self):
        import datetime
        raw = {"imo": "3333333", "eta": "2024-05-01T06:00:00Z"}
        record = parse_vessel(raw)
        assert isinstance(record.eta, datetime.datetime)

    def test_alternative_field_names(self):
        raw = {
            "imoNumber": "4444444",
            "shipname": "ALT NAMES",
            "shiptype": "chemical tanker",
            "latitude": 10.0,
            "longitude": 20.0,
            "sog": 5.5,
            "cog": 90,
        }
        record = parse_vessel(raw)
        assert record.imo == "4444444"
        assert record.name == "ALT NAMES"
        assert record.vessel_type == "Chemical"
        assert record.lat == pytest.approx(10.0)
        assert record.speed == pytest.approx(5.5)
        assert record.heading == 90


# ---------------------------------------------------------------------------
# parse_vessels (bulk)
# ---------------------------------------------------------------------------

class TestParseVessels:
    def test_parses_fixture(self, sample_raw):
        records = parse_vessels(sample_raw)
        # 4 valid records (1 has no identifiers and should be skipped)
        assert len(records) == 4

    def test_skips_non_dict(self):
        raw = [{"imo": "1"}, "not-a-dict", 42, None, {"imo": "2"}]
        records = parse_vessels(raw)
        assert len(records) == 2

    def test_empty_list(self):
        assert parse_vessels([]) == []
