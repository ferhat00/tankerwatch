"""
test_db.py – Unit tests for tankerwatch.db: port proximity matching
and port visit inference logic.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from tankerwatch.db import (
    Port,
    PortVisit,
    Position,
    Vessel,
    _haversine_km,
    get_session_factory,
    infer_port_visits,
    init_db,
    nearest_port,
    save_vessels,
)
from tankerwatch.parser import VesselRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path):
    """Return a path to a fresh temporary SQLite database."""
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return db_path


@pytest.fixture()
def _rotterdam():
    return Port(id=1, name="Rotterdam", unlocode="NLRTM", lat=51.94, lon=4.14,
                port_type="crude_import", country="NL")


@pytest.fixture()
def _singapore():
    return Port(id=2, name="Singapore Jurong Island", unlocode="SGJUR",
                lat=1.27, lon=103.70, port_type="crude_import", country="SG")


# ---------------------------------------------------------------------------
# Haversine distance
# ---------------------------------------------------------------------------

class TestHaversine:
    def test_same_point(self):
        assert _haversine_km(51.94, 4.14, 51.94, 4.14) == pytest.approx(0.0, abs=1e-9)

    def test_rotterdam_to_antwerp(self):
        # Rotterdam ↔ Antwerp is ~50-60 km
        d = _haversine_km(51.94, 4.14, 51.26, 4.40)
        assert 50 < d < 80

    def test_rotterdam_to_singapore(self):
        d = _haversine_km(51.94, 4.14, 1.27, 103.70)
        assert d > 9000


# ---------------------------------------------------------------------------
# Port proximity matching
# ---------------------------------------------------------------------------

class TestNearestPort:
    def test_exact_match(_self, _rotterdam, _singapore):
        ports = [_rotterdam, _singapore]
        result = nearest_port(51.94, 4.14, ports, max_km=10.0)
        assert result is not None
        assert result.name == "Rotterdam"

    def test_within_radius(_self, _rotterdam):
        # Position 2 km from Rotterdam
        result = nearest_port(51.95, 4.15, [_rotterdam], max_km=10.0)
        assert result is not None

    def test_outside_radius(_self, _rotterdam):
        # Position in Berlin – far from Rotterdam
        result = nearest_port(52.52, 13.41, [_rotterdam], max_km=10.0)
        assert result is None

    def test_empty_ports_list(_self):
        result = nearest_port(51.94, 4.14, [], max_km=10.0)
        assert result is None

    def test_picks_nearest(_self, _rotterdam, _singapore):
        # Point very close to Singapore but far from Rotterdam
        result = nearest_port(1.28, 103.71, [_rotterdam, _singapore], max_km=20.0)
        assert result.name == "Singapore Jurong Island"


# ---------------------------------------------------------------------------
# Port visit inference
# ---------------------------------------------------------------------------

def _make_vessel(imo: str = "TEST001") -> VesselRecord:
    return VesselRecord(
        imo=imo, mmsi="", name="Test Vessel", vessel_type="VLCC",
        vessel_type_raw="VLCC", dwt=200000, built_year=2000, flag="PA",
        lat=None, lon=None, speed=None, heading=None, nav_status=None,
        destination=None, eta=None, draught=None,
    )


class TestPortVisitInference:
    def test_stationary_vessel_creates_visit(self, tmp_db):
        """A vessel that stays near Rotterdam for 3+ readings should trigger a visit."""
        factory = get_session_factory(tmp_db)
        base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        with factory() as session:
            session.add(Vessel(imo="V001", name="Stationary", vessel_type="VLCC",
                               vessel_type_raw="VLCC", updated_at=base_time))
            # 4 readings at Rotterdam (slow speed)
            for i in range(4):
                session.add(Position(
                    imo="V001",
                    scraped_at=base_time + timedelta(hours=i),
                    lat=51.94, lon=4.14,
                    speed=0.2,
                ))
            session.commit()

        new_visits = infer_port_visits(
            db_path=tmp_db,
            proximity_km=10.0,
            min_stationary_readings=3,
            stationary_speed_knots=0.5,
        )
        assert new_visits >= 1

        with factory() as session:
            visits = session.query(PortVisit).filter_by(imo="V001").all()
        assert len(visits) >= 1
        assert visits[0].port_name == "Rotterdam"

    def test_moving_vessel_no_visit(self, tmp_db):
        """A vessel that always moves fast should not create any visits."""
        factory = get_session_factory(tmp_db)
        base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        with factory() as session:
            session.add(Vessel(imo="V002", name="Speedy", vessel_type="MR",
                               vessel_type_raw="MR", updated_at=base_time))
            for i in range(5):
                session.add(Position(
                    imo="V002",
                    scraped_at=base_time + timedelta(hours=i),
                    lat=51.94 + i * 0.5, lon=4.14 + i * 0.5,
                    speed=14.0,
                ))
            session.commit()

        new_visits = infer_port_visits(
            db_path=tmp_db,
            min_stationary_readings=3,
            stationary_speed_knots=0.5,
        )
        assert new_visits == 0

    def test_departure_sets_departed_at(self, tmp_db):
        """After the vessel departs, departed_at should be set."""
        factory = get_session_factory(tmp_db)
        base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        with factory() as session:
            session.add(Vessel(imo="V003", name="Depart Me", vessel_type="Suezmax",
                               vessel_type_raw="Suezmax", updated_at=base_time))
            # 3 stationary readings
            for i in range(3):
                session.add(Position(
                    imo="V003",
                    scraped_at=base_time + timedelta(hours=i),
                    lat=51.94, lon=4.14,
                    speed=0.1,
                ))
            # 1 underway reading
            session.add(Position(
                imo="V003",
                scraped_at=base_time + timedelta(hours=4),
                lat=51.94, lon=4.14,
                speed=10.0,
            ))
            session.commit()

        infer_port_visits(
            db_path=tmp_db,
            proximity_km=10.0,
            min_stationary_readings=3,
            stationary_speed_knots=0.5,
            departure_speed_knots=1.5,
        )

        with factory() as session:
            visits = session.query(PortVisit).filter_by(imo="V003").all()

        assert len(visits) >= 1
        assert visits[0].departed_at is not None


# ---------------------------------------------------------------------------
# save_vessels round-trip
# ---------------------------------------------------------------------------

class TestSaveVessels:
    def test_upsert(self, tmp_db):
        record = _make_vessel("IMO999")
        record.lat = 26.64
        record.lon = 50.16
        record.speed = 0.5

        stats = save_vessels([record], db_path=tmp_db)
        assert stats["vessels_upserted"] == 1
        assert stats["positions_inserted"] == 1

        # Upsert again – should not raise
        stats2 = save_vessels([record], db_path=tmp_db)
        assert stats2["vessels_upserted"] == 1
