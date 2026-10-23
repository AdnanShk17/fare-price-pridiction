"""SQLite storage for saved fare comparisons ("bookings")."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

import pandas as pd

DB_PATH = Path(os.environ.get("FARE_DB_PATH", Path(__file__).resolve().parent / "taxi.db"))

_TEXT_LIMIT = 500

# Columns added after the first release; migrated automatically on old databases.
_MIGRATIONS = {
    "session_id": "TEXT",
    "vehicle_type": "TEXT",
    "trip_time": "TEXT",
}


@contextmanager
def _connect(db_path: Optional[os.PathLike] = None) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(db_path or DB_PATH), timeout=10)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Optional[os.PathLike] = None) -> None:
    with _connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cab_bookings (
                booking_id INTEGER PRIMARY KEY AUTOINCREMENT,
                pickup TEXT,
                dropoff TEXT,
                stops TEXT,
                distance_km REAL,
                duration_min REAL,
                traffic_level TEXT,
                weather TEXT,
                ola_fare REAL,
                uber_fare REAL,
                rapido_fare REAL,
                kaali_peeli_fare REAL,
                ml_fare REAL,
                booking_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        existing = {row[1] for row in conn.execute("PRAGMA table_info(cab_bookings)")}
        for column, ctype in _MIGRATIONS.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE cab_bookings ADD COLUMN {column} {ctype}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bookings_session ON cab_bookings(session_id)")


def _num_or_none(value):
    return None if value is None else float(value)


def _text(value) -> str:
    return ("" if value is None else str(value)).strip()[:_TEXT_LIMIT]


def save_booking(pickup, dropoff, stops, distance, duration, traffic, weather,
                 ola, uber, rapido, kp, ml, vehicle_type="", session_id="", trip_time="",
                 db_path: Optional[os.PathLike] = None) -> int:
    """Insert a booking and return its id. Parameterised query (no SQL injection)."""
    with _connect(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO cab_bookings
               (pickup, dropoff, stops, distance_km, duration_min, traffic_level, weather,
                ola_fare, uber_fare, rapido_fare, kaali_peeli_fare, ml_fare, vehicle_type, session_id, trip_time)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (_text(pickup), _text(dropoff), _text(stops), float(distance), float(duration),
             _text(traffic), _text(weather), _num_or_none(ola), _num_or_none(uber), _num_or_none(rapido), _num_or_none(kp),
             float(ml), _text(vehicle_type), _text(session_id), _text(trip_time)),
        )
        return int(cur.lastrowid)


def get_bookings(session_id: Optional[str] = None, limit: int = 500,
                 db_path: Optional[os.PathLike] = None) -> pd.DataFrame:
    """Newest first. Pass a session_id to show only that visitor's bookings."""
    query = "SELECT * FROM cab_bookings"
    params: list = []
    if session_id is not None:
        query += " WHERE session_id = ?"
        params.append(session_id)
    query += " ORDER BY booking_id DESC LIMIT ?"
    params.append(int(limit))
    with _connect(db_path) as conn:
        return pd.read_sql_query(query, conn, params=params)
