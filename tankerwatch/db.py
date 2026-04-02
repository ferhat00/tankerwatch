"""
db.py – SQLAlchemy ORM models and database helpers for TankerWatch.

Tables:
  - vessels      : master vessel registry
  - positions    : time-series position snapshots
  - port_visits  : inferred port calls
  - ports        : reference table of ~50 major oil/gas terminals
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
    select,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

if TYPE_CHECKING:
    from tankerwatch.parser import VesselRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ORM base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Vessel(Base):
    __tablename__ = "vessels"

    imo = Column(String, primary_key=True)
    mmsi = Column(String, nullable=True)
    name = Column(String, nullable=True)
    vessel_type = Column(String, nullable=True)
    vessel_type_raw = Column(String, nullable=True)
    dwt = Column(Integer, nullable=True)
    built_year = Column(Integer, nullable=True)
    flag = Column(String, nullable=True)
    updated_at = Column(DateTime, nullable=True)

    positions = relationship("Position", back_populates="vessel", lazy="dynamic")
    port_visits = relationship("PortVisit", back_populates="vessel", lazy="dynamic")


class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    imo = Column(String, ForeignKey("vessels.imo"), nullable=False, index=True)
    scraped_at = Column(DateTime, nullable=False)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    speed = Column(Float, nullable=True)
    heading = Column(Integer, nullable=True)
    nav_status = Column(String, nullable=True)
    destination = Column(String, nullable=True)
    eta = Column(DateTime, nullable=True)
    draught = Column(Float, nullable=True)

    vessel = relationship("Vessel", back_populates="positions")


class Port(Base):
    __tablename__ = "ports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    unlocode = Column(String, nullable=True)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    port_type = Column(String, nullable=True)  # crude_export, crude_import, lng_export, etc.
    country = Column(String, nullable=True)

    port_visits = relationship("PortVisit", back_populates="port", lazy="dynamic")


class PortVisit(Base):
    __tablename__ = "port_visits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    imo = Column(String, ForeignKey("vessels.imo"), nullable=False, index=True)
    port_id = Column(Integer, ForeignKey("ports.id"), nullable=True)
    port_name = Column(String, nullable=True)
    port_unlocode = Column(String, nullable=True)
    arrived_at = Column(DateTime, nullable=False)
    departed_at = Column(DateTime, nullable=True)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)

    vessel = relationship("Vessel", back_populates="port_visits")
    port = relationship("Port", back_populates="port_visits")


# ---------------------------------------------------------------------------
# Reference port data (~50 major oil/gas terminals)
# ---------------------------------------------------------------------------

REFERENCE_PORTS = [
    # Middle East
    {"name": "Ras Tanura", "unlocode": "SARAT", "lat": 26.64, "lon": 50.16, "port_type": "crude_export", "country": "SA"},
    {"name": "Kharg Island", "unlocode": "IRKHK", "lat": 29.24, "lon": 50.32, "port_type": "crude_export", "country": "IR"},
    {"name": "Basrah Oil Terminal", "unlocode": "IQBSR", "lat": 29.68, "lon": 48.78, "port_type": "crude_export", "country": "IQ"},
    {"name": "Fujairah", "unlocode": "AEFUJ", "lat": 25.12, "lon": 56.34, "port_type": "crude_import", "country": "AE"},
    {"name": "Ruwais", "unlocode": "AERUW", "lat": 24.11, "lon": 52.73, "port_type": "crude_export", "country": "AE"},
    {"name": "Sitra", "unlocode": "BHSIT", "lat": 26.15, "lon": 50.63, "port_type": "crude_export", "country": "BH"},
    {"name": "Mina Al Ahmadi", "unlocode": "KWMAA", "lat": 29.05, "lon": 48.13, "port_type": "crude_export", "country": "KW"},
    {"name": "Jebel Ali", "unlocode": "AEJEA", "lat": 24.98, "lon": 55.04, "port_type": "crude_import", "country": "AE"},
    {"name": "Yanbu", "unlocode": "SAYNB", "lat": 24.09, "lon": 38.06, "port_type": "crude_export", "country": "SA"},
    # Europe
    {"name": "Rotterdam", "unlocode": "NLRTM", "lat": 51.94, "lon": 4.14, "port_type": "crude_import", "country": "NL"},
    {"name": "Antwerp", "unlocode": "BEANR", "lat": 51.26, "lon": 4.40, "port_type": "crude_import", "country": "BE"},
    {"name": "Primorsk", "unlocode": "RUPMK", "lat": 60.37, "lon": 28.62, "port_type": "crude_export", "country": "RU"},
    {"name": "Novorossiysk", "unlocode": "RUNVS", "lat": 44.72, "lon": 37.77, "port_type": "crude_export", "country": "RU"},
    {"name": "Gdansk", "unlocode": "PLGDN", "lat": 54.35, "lon": 18.65, "port_type": "crude_import", "country": "PL"},
    {"name": "Wilhelmshaven", "unlocode": "DEWIL", "lat": 53.53, "lon": 8.15, "port_type": "crude_import", "country": "DE"},
    {"name": "Fos-sur-Mer", "unlocode": "FRFOS", "lat": 43.43, "lon": 4.86, "port_type": "crude_import", "country": "FR"},
    {"name": "Trieste", "unlocode": "ITTRS", "lat": 45.65, "lon": 13.78, "port_type": "crude_import", "country": "IT"},
    # North America
    {"name": "Houston Ship Channel", "unlocode": "USHSC", "lat": 29.73, "lon": -95.27, "port_type": "crude_import", "country": "US"},
    {"name": "Corpus Christi", "unlocode": "USCRP", "lat": 27.81, "lon": -97.40, "port_type": "crude_export", "country": "US"},
    {"name": "Sabine Pass LNG", "unlocode": "USSAB", "lat": 29.73, "lon": -93.87, "port_type": "lng_export", "country": "US"},
    {"name": "Freeport LNG", "unlocode": "USFPT", "lat": 28.94, "lon": -95.35, "port_type": "lng_export", "country": "US"},
    {"name": "Cameron LNG", "unlocode": "USCAM", "lat": 29.78, "lon": -93.32, "port_type": "lng_export", "country": "US"},
    {"name": "Louisiana Offshore Oil Port", "unlocode": "USLOOP", "lat": 28.89, "lon": -90.02, "port_type": "crude_import", "country": "US"},
    {"name": "Port Arthur", "unlocode": "USPAU", "lat": 29.87, "lon": -93.92, "port_type": "crude_import", "country": "US"},
    {"name": "Vancouver", "unlocode": "CAVAN", "lat": 49.29, "lon": -123.11, "port_type": "crude_export", "country": "CA"},
    # Asia Pacific
    {"name": "Singapore Jurong Island", "unlocode": "SGJUR", "lat": 1.27, "lon": 103.70, "port_type": "crude_import", "country": "SG"},
    {"name": "Ulsan", "unlocode": "KRULS", "lat": 35.50, "lon": 129.39, "port_type": "crude_import", "country": "KR"},
    {"name": "Yeosu", "unlocode": "KRYOS", "lat": 34.74, "lon": 127.73, "port_type": "crude_import", "country": "KR"},
    {"name": "Ningbo", "unlocode": "CNNBO", "lat": 29.87, "lon": 121.55, "port_type": "crude_import", "country": "CN"},
    {"name": "Qingdao", "unlocode": "CNTAO", "lat": 36.07, "lon": 120.38, "port_type": "crude_import", "country": "CN"},
    {"name": "Jieyang Huizhou", "unlocode": "CNHUI", "lat": 22.78, "lon": 114.72, "port_type": "crude_import", "country": "CN"},
    {"name": "JERA Sodegaura LNG", "unlocode": "JPSOD", "lat": 35.50, "lon": 139.98, "port_type": "lng_import", "country": "JP"},
    {"name": "Senboku LNG Terminal", "unlocode": "JPSEN", "lat": 34.56, "lon": 135.48, "port_type": "lng_import", "country": "JP"},
    {"name": "Sikka", "unlocode": "INSIK", "lat": 22.43, "lon": 70.07, "port_type": "crude_import", "country": "IN"},
    {"name": "Vadinar", "unlocode": "INVAD", "lat": 22.47, "lon": 69.64, "port_type": "crude_import", "country": "IN"},
    {"name": "Paradip", "unlocode": "INPRD", "lat": 20.32, "lon": 86.61, "port_type": "crude_import", "country": "IN"},
    {"name": "Mailiao", "unlocode": "TWMAI", "lat": 23.77, "lon": 120.18, "port_type": "crude_import", "country": "TW"},
    # Africa
    {"name": "Saldanha Bay", "unlocode": "ZASAL", "lat": -33.01, "lon": 17.97, "port_type": "crude_export", "country": "ZA"},
    {"name": "Bonny Oil Terminal", "unlocode": "NGBON", "lat": 4.44, "lon": 7.15, "port_type": "crude_export", "country": "NG"},
    {"name": "Escravos", "unlocode": "NGESC", "lat": 5.54, "lon": 5.17, "port_type": "crude_export", "country": "NG"},
    {"name": "Cabinda", "unlocode": "AOCAB", "lat": -5.55, "lon": 12.19, "port_type": "crude_export", "country": "AO"},
    {"name": "Ras Lanuf", "unlocode": "LYRAS", "lat": 30.48, "lon": 18.57, "port_type": "crude_export", "country": "LY"},
    # Americas
    {"name": "Puerto La Cruz", "unlocode": "VEPLC", "lat": 10.21, "lon": -64.64, "port_type": "crude_export", "country": "VE"},
    {"name": "Jose Terminal", "unlocode": "VEJOS", "lat": 10.17, "lon": -64.94, "port_type": "crude_export", "country": "VE"},
    {"name": "Cayo Arcas", "unlocode": "MXCAY", "lat": 19.99, "lon": -91.93, "port_type": "crude_export", "country": "MX"},
    {"name": "Pajaros Island", "unlocode": "MXPAJ", "lat": 19.07, "lon": -96.09, "port_type": "crude_export", "country": "MX"},
    # Australia / Oceania
    {"name": "Darwin DLNG", "unlocode": "AUDLNG", "lat": -12.47, "lon": 130.84, "port_type": "lng_export", "country": "AU"},
    {"name": "Gladstone LNG", "unlocode": "AUGLT", "lat": -23.86, "lon": 151.26, "port_type": "lng_export", "country": "AU"},
    {"name": "Dampier", "unlocode": "AUDPB", "lat": -20.66, "lon": 116.72, "port_type": "lng_export", "country": "AU"},
    {"name": "Ras Laffan LNG", "unlocode": "QARAS", "lat": 25.93, "lon": 51.57, "port_type": "lng_export", "country": "QA"},
]


# ---------------------------------------------------------------------------
# Engine / session factory
# ---------------------------------------------------------------------------

_engines: dict[str, object] = {}
_session_factories: dict[str, object] = {}


def get_engine(db_path: str = "data/tankerwatch.db"):
    if db_path not in _engines:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{db_path}"
        engine = create_engine(url, echo=False, connect_args={"check_same_thread": False})

        # Enable WAL mode for better concurrent read performance
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_conn, _connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

        _engines[db_path] = engine
    return _engines[db_path]


def get_session_factory(db_path: str = "data/tankerwatch.db"):
    if db_path not in _session_factories:
        _session_factories[db_path] = sessionmaker(
            bind=get_engine(db_path), expire_on_commit=False
        )
    return _session_factories[db_path]


def init_db(db_path: str = "data/tankerwatch.db") -> None:
    """Create all tables and seed the ports reference table."""
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    _seed_ports(engine)
    logger.info("Database initialised at %s", db_path)


def _seed_ports(engine) -> None:
    """Insert reference ports if the table is empty."""
    with Session(engine) as session:
        existing = session.execute(select(Port)).scalars().first()
        if existing is not None:
            return
        for p in REFERENCE_PORTS:
            session.add(Port(**p))
        session.commit()
        logger.info("Seeded %d reference ports", len(REFERENCE_PORTS))


# ---------------------------------------------------------------------------
# Upsert helpers
# ---------------------------------------------------------------------------

def upsert_vessel(session: Session, record: "VesselRecord") -> None:
    """Insert or update a Vessel row from a VesselRecord."""
    existing = session.get(Vessel, record.imo)
    now = datetime.now(timezone.utc)
    if existing is None:
        session.add(Vessel(
            imo=record.imo,
            mmsi=record.mmsi,
            name=record.name,
            vessel_type=record.vessel_type,
            vessel_type_raw=record.vessel_type_raw,
            dwt=record.dwt,
            built_year=record.built_year,
            flag=record.flag,
            updated_at=now,
        ))
    else:
        existing.mmsi = record.mmsi or existing.mmsi
        existing.name = record.name or existing.name
        existing.vessel_type = record.vessel_type or existing.vessel_type
        existing.vessel_type_raw = record.vessel_type_raw or existing.vessel_type_raw
        existing.dwt = record.dwt or existing.dwt
        existing.built_year = record.built_year or existing.built_year
        existing.flag = record.flag or existing.flag
        existing.updated_at = now


def insert_position(session: Session, record: "VesselRecord", scraped_at: datetime | None = None) -> None:
    """Insert a Position snapshot for the given VesselRecord."""
    if record.lat is None and record.lon is None:
        return
    session.add(Position(
        imo=record.imo,
        scraped_at=scraped_at or datetime.now(timezone.utc),
        lat=record.lat,
        lon=record.lon,
        speed=record.speed,
        heading=record.heading,
        nav_status=record.nav_status,
        destination=record.destination,
        eta=record.eta,
        draught=record.draught,
    ))


def save_vessels(records: list["VesselRecord"], db_path: str = "data/tankerwatch.db") -> dict[str, int]:
    """
    Persist a list of VesselRecords to the database.
    Returns a dict with counts: vessels_upserted, positions_inserted.
    """
    factory = get_session_factory(db_path)
    scraped_at = datetime.now(timezone.utc)
    vessels_upserted = 0
    positions_inserted = 0

    with factory() as session:
        for record in records:
            upsert_vessel(session, record)
            vessels_upserted += 1
            if record.lat is not None or record.lon is not None:
                insert_position(session, record, scraped_at)
                positions_inserted += 1
        session.commit()

    logger.info("Saved %d vessels, %d positions", vessels_upserted, positions_inserted)
    return {"vessels_upserted": vessels_upserted, "positions_inserted": positions_inserted}


# ---------------------------------------------------------------------------
# Port visit inference
# ---------------------------------------------------------------------------

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def nearest_port(
    lat: float,
    lon: float,
    ports: list[Port],
    max_km: float = 10.0,
) -> Port | None:
    """Return the nearest Port within max_km, or None."""
    best: Port | None = None
    best_dist = float("inf")
    for port in ports:
        d = _haversine_km(lat, lon, port.lat, port.lon)
        if d < best_dist:
            best_dist = d
            best = port
    if best_dist <= max_km:
        return best
    return None


def infer_port_visits(
    db_path: str = "data/tankerwatch.db",
    proximity_km: float = 10.0,
    min_stationary_readings: int = 3,
    stationary_speed_knots: float = 0.5,
    departure_speed_knots: float = 1.5,
) -> int:
    """
    Scan positions table and create/update port_visits records.

    Returns number of new visits opened.
    """
    factory = get_session_factory(db_path)
    new_visits = 0

    with factory() as session:
        all_ports = session.execute(select(Port)).scalars().all()
        vessels_stmt = select(Vessel.imo)
        vessel_imos = session.execute(vessels_stmt).scalars().all()

        for imo in vessel_imos:
            positions_stmt = (
                select(Position)
                .where(Position.imo == imo)
                .order_by(Position.scraped_at)
            )
            positions = session.execute(positions_stmt).scalars().all()
            if len(positions) < min_stationary_readings:
                continue

            stationary_streak: list[Position] = []
            open_visit: PortVisit | None = None

            for pos in positions:
                speed = pos.speed if pos.speed is not None else 99.0

                if speed <= stationary_speed_knots and pos.lat is not None and pos.lon is not None:
                    stationary_streak.append(pos)

                    if len(stationary_streak) >= min_stationary_readings and open_visit is None:
                        # Try to match a nearby port
                        port = nearest_port(pos.lat, pos.lon, all_ports, proximity_km)
                        open_visit = PortVisit(
                            imo=imo,
                            port_id=port.id if port else None,
                            port_name=port.name if port else "Unknown",
                            port_unlocode=port.unlocode if port else None,
                            arrived_at=stationary_streak[0].scraped_at,
                            lat=pos.lat,
                            lon=pos.lon,
                        )
                        session.add(open_visit)
                        new_visits += 1
                else:
                    stationary_streak = []
                    if open_visit is not None and speed > departure_speed_knots:
                        open_visit.departed_at = pos.scraped_at
                        open_visit = None

        session.commit()

    logger.info("Port visit inference complete – %d new visits", new_visits)
    return new_visits
