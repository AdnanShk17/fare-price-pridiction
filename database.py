import sqlite3
import pandas as pd

DB_NAME = "taxi.db"

# ---------------------------------------------------
# Create Database & Table
# ---------------------------------------------------

def init_db():

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
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

    conn.commit()
    conn.close()


# ---------------------------------------------------
# View Database
# ---------------------------------------------------

def get_all_bookings():

    conn = sqlite3.connect(DB_NAME)

    df = pd.read_sql_query(
        "SELECT * FROM cab_bookings ORDER BY booking_id DESC",
        conn
    )

    conn.close()

    return df
# ---------------------------------------------------
# Save Booking
# ---------------------------------------------------

def save_booking(
    pickup,
    dropoff,
    stops,
    distance,
    duration,
    traffic,
    weather,
    ola,
    uber,
    rapido,
    kp,
    ml
):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO cab_bookings (
            pickup,
            dropoff,
            stops,
            distance_km,
            duration_min,
            traffic_level,
            weather,
            ola_fare,
            uber_fare,
            rapido_fare,
            kaali_peeli_fare,
            ml_fare
        )
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        pickup,
        dropoff,
        stops,
        distance,
        duration,
        traffic,
        weather,
        ola,
        uber,
        rapido,
        kp,
        ml
    ))

    conn.commit()
    conn.close()