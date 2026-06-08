import sqlite3
import os
from typing import List, Dict, Any, Optional
from src.config import DATABASE_PATH, logger

def get_db_connection() -> sqlite3.Connection:
    """Creates and returns a connection to the SQLite database with row_factory enabled and FK constraints turned on."""
    # Ensure directory exists
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db(schema_path: str = "schema.sql") -> None:
    """Initializes the database using the schema file and seeds the initial data if empty."""
    logger.info("Initializing database...")
    if not os.path.exists(schema_path):
        logger.error(f"Schema file not found at {schema_path}!")
        return

    with open(schema_path, 'r') as f:
        schema_sql = f.read()

    with get_db_connection() as conn:
        conn.executescript(schema_sql)
        conn.commit()
    
    logger.info("Schema applied successfully. Seeding initial data...")
    seed_initial_data()
    
    # Run migrations
    run_migrations()

def run_migrations() -> None:
    """Runs database migrations to update existing databases with new data/structures."""
    logger.info("Running database migrations...")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Create migrations table if it doesn't exist (in case schema.sql wasn't run)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS migrations (
                name TEXT PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        
        # Check if thodupuzha migration has run
        cursor.execute("SELECT 1 FROM migrations WHERE name = ?", ("seed_thodupuzha_schedules",))
        if cursor.fetchone():
            logger.info("Migration 'seed_thodupuzha_schedules' already applied.")
            return

        logger.info("Applying migration 'seed_thodupuzha_schedules'...")
        
        # Get destination IDs
        cursor.execute("SELECT id, name FROM destinations")
        dest_ids = {row["name"]: row["id"] for row in cursor.fetchall()}
        
        # Make sure Thodupuzha and Njarakkadu destinations exist
        for dest in ["Thodupuzha", "Njarakkadu"]:
            if dest not in dest_ids:
                cursor.execute("INSERT OR IGNORE INTO destinations (name) VALUES (?)", (dest,))
        
        cursor.execute("SELECT id, name FROM destinations")
        dest_ids = {row["name"]: row["id"] for row in cursor.fetchall()}
        
        # Make sure Thodupuzha (Service) bus exists
        cursor.execute("SELECT id FROM buses WHERE name = ?", ("Thodupuzha (Service)",))
        row = cursor.fetchone()
        if row:
            bus_id = row["id"]
        else:
            cursor.execute("INSERT INTO buses (name, type) VALUES (?, ?)", ("Thodupuzha (Service)", "Private"))
            bus_id = cursor.lastrowid
            
        # Thodupuzha destination schedules (Njarakkadu -> Thodupuzha)
        thodupuzha_schedules = [
            ("05:35", 50, "daily"),
            ("06:45", 50, "daily"),
            ("07:40", 50, "daily"),
            ("08:30", 50, "daily"),
            ("08:50", 50, "daily"),
            ("09:15", 50, "daily"),
            ("10:05", 50, "daily"),
            ("11:05", 50, "daily"),
            ("12:05", 50, "daily"),
            ("12:40", 50, "daily"),
            ("13:15", 50, "daily"),
            ("14:05", 50, "daily"),
            ("14:50", 50, "daily"),
            ("15:15", 50, "daily"),
            ("15:50", 50, "daily"),
            ("16:15", 50, "daily"),
            ("17:05", 50, "daily"),
            ("17:40", 50, "daily")
        ]
        
        for arr_time, duration, day_type in thodupuzha_schedules:
            cursor.execute("""
                INSERT OR IGNORE INTO schedules (destination_id, bus_id, arrival_time, travel_duration, day_type, from_point)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (dest_ids["Thodupuzha"], bus_id, arr_time, duration, day_type, "Njarakkadu"))
            
        # Njarakkadu destination schedules (Thodupuzha -> Njarakkadu)
        thodupuzha_to_njarakkadu_schedules = [
            ("07:35", 50, "daily"),
            ("08:30", 50, "daily"),
            ("09:20", 50, "daily"),
            ("09:35", 50, "daily"),
            ("10:00", 50, "daily"),
            ("11:00", 50, "daily"),
            ("11:55", 50, "daily"),
            ("12:25", 50, "daily"),
            ("12:55", 50, "daily"),
            ("13:45", 50, "daily"),
            ("14:10", 50, "daily"),
            ("15:00", 50, "daily"),
            ("15:30", 50, "daily"),
            ("16:15", 50, "daily"),
            ("16:30", 50, "daily"),
            ("16:50", 50, "daily"),
            ("17:55", 50, "daily"),
            ("18:35", 50, "daily"),
            ("19:15", 50, "daily")
        ]
        
        for arr_time, duration, day_type in thodupuzha_to_njarakkadu_schedules:
            cursor.execute("""
                INSERT OR IGNORE INTO schedules (destination_id, bus_id, arrival_time, travel_duration, day_type, from_point)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (dest_ids["Njarakkadu"], bus_id, arr_time, duration, day_type, "Thodupuzha"))
            
        # Record migration
        cursor.execute("INSERT INTO migrations (name) VALUES (?)", ("seed_thodupuzha_schedules",))
        conn.commit()
        logger.info("Migration 'seed_thodupuzha_schedules' applied successfully.")


def seed_initial_data() -> None:
    """Seeds the database with required destinations, buses, and new schedules from the user's timetable."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Seed Destinations
        destinations = ["Muvattupuzha", "Kaliyar", "Kothamangalam", "Thodupuzha", "Njarakkadu"]
        for dest in destinations:
            cursor.execute("INSERT OR IGNORE INTO destinations (name) VALUES (?)", (dest,))
            
        cursor.execute("SELECT id, name FROM destinations")
        dest_ids = {row["name"]: row["id"] for row in cursor.fetchall()}
        
        # 2. Seed Buses (unique names across all lists)
        buses = [
            ("Jeeva", "Private"),
            ("RoseLand", "Private"),
            ("St. George", "Private"),
            ("KSRTC (Ernakulam)", "KSRTC"),
            ("Sreelakshmi", "Private"),
            ("Sreekutty", "Private"),
            ("Meeras", "Private"),
            ("Greenland", "Private"),
            ("SMS", "Private"),
            ("Thodupuzha (Service)", "Private"),
            ("KSRTC Kattappana", "KSRTC")
        ]
        for name, bus_type in buses:
            cursor.execute("INSERT OR IGNORE INTO buses (name, type) VALUES (?, ?)", (name, bus_type))
            
        cursor.execute("SELECT id, name FROM buses")
        bus_ids = {row["name"]: row["id"] for row in cursor.fetchall()}
        
        # 3. Seed Schedules (only if table is empty to preserve admin edits!)
        cursor.execute("SELECT COUNT(*) FROM schedules")
        if cursor.fetchone()[0] > 0:
            logger.info("Schedules table is already populated. Skipping seeding to preserve admin data.")
            return
        
        # Data for Muvattupuzha (Towards Muvattupuzha)
        muvattupuzha_schedules = [
            ("Jeeva", "05:50", 45, "daily"),
            ("RoseLand", "06:25", 45, "daily"),
            ("St. George", "06:40", 45, "daily"),
            ("Jeeva", "06:50", 45, "daily"),
            ("RoseLand", "07:15", 45, "daily"),
            ("St. George", "07:20", 45, "daily"),
            ("Jeeva", "07:35", 45, "daily"),
            ("KSRTC (Ernakulam)", "07:40", 45, "daily"),
            ("Sreelakshmi", "07:50", 45, "daily"),
            ("Sreekutty", "07:55", 45, "daily"),
            ("Meeras", "08:10", 45, "daily"),
            ("Meeras", "08:35", 45, "daily"),
            ("Jeeva", "08:50", 45, "daily"),
            ("Jeeva", "09:05", 45, "daily"),
            ("Jeeva", "09:20", 45, "daily"),
            ("St. George", "09:35", 45, "daily"),
            ("Greenland", "09:50", 45, "daily"),
            ("RoseLand", "10:05", 45, "daily"),
            ("Jeeva", "10:35", 45, "daily"),
            ("Sreelakshmi", "10:50", 45, "daily"),
            ("Sreekutty", "11:15", 45, "daily"),
            ("Meeras", "11:35", 45, "daily"),
            ("Meeras", "11:55", 45, "daily"),
            ("Jeeva", "12:15", 45, "daily"),
            ("Jeeva", "12:35", 45, "daily"),
            ("Jeeva", "13:10", 45, "daily"),
            ("St. George", "13:20", 45, "daily"),
            ("RoseLand", "13:40", 45, "daily"),
            ("Greenland", "14:05", 45, "daily"),
            ("St. George", "14:15", 45, "daily"),
            ("Jeeva", "14:35", 45, "daily"),
            ("Sreekutty", "14:50", 45, "daily"),
            ("Meeras", "15:05", 45, "daily"),
            ("Sreelakshmi", "15:20", 45, "daily"),
            ("Jeeva", "15:40", 45, "daily"),
            ("Jeeva", "16:05", 45, "daily"),
            ("Meeras", "16:25", 45, "daily"),
            ("Jeeva", "16:40", 45, "daily"),
            ("RoseLand", "17:05", 45, "daily"),
            ("Meeras", "17:25", 45, "daily"),
            ("St. George", "17:35", 45, "daily"),
            ("Greenland", "17:50", 45, "daily"),
            ("Jeeva", "18:10", 45, "daily"),
            ("Sreekutty", "18:30", 45, "daily"),
            ("Jeeva", "18:40", 45, "daily"),
            ("Sreelakshmi", "19:15", 45, "daily")
        ]
        
        # Data for Kothamangalam (Towards Kothamangalam)
        kothamangalam_schedules = [
            ("Jeeva", "06:15", 40, "daily"),
            ("St. George", "06:50", 40, "daily"),
            ("Jeeva", "09:05", 40, "daily"),
            ("St. George", "09:50", 40, "daily"),
            ("SMS", "10:30", 40, "daily"),
            ("Jeeva", "12:50", 40, "daily"),
            ("St. George", "13:50", 40, "daily"),
            ("Jeeva", "15:50", 40, "daily"),
            ("St. George", "17:20", 40, "daily")
        ]
        
        # Data for Kaliyar (Towards Kaliyar)
        kaliyar_schedules = [
            ("Sreelakshmi", "07:10", 50, "daily"),
            ("Thodupuzha (Service)", "07:35", 50, "daily"),
            ("Meeras", "07:50", 50, "daily"),
            ("Jeeva", "08:15", 50, "daily"),
            ("Jeeva", "08:35", 50, "daily"),
            ("St. George", "08:40", 50, "daily"),
            ("Greenland", "08:55", 50, "daily"),
            ("St. George", "09:10", 50, "daily"),
            ("RoseLand", "09:20", 50, "daily"),
            ("Jeeva", "09:50", 50, "daily"),
            ("Sreelakshmi", "10:10", 50, "daily"),
            ("Sreekutty", "10:30", 50, "daily"),
            ("Meeras", "10:50", 50, "daily"),
            ("Meeras", "11:10", 50, "daily"),
            ("Jeeva", "11:25", 50, "daily"),
            ("Jeeva", "11:50", 50, "daily"),
            ("Jeeva", "12:05", 50, "daily"),
            ("St. George", "12:20", 50, "daily"),
            ("RoseLand", "12:30", 50, "daily"),
            ("St. George", "12:50", 50, "daily"),
            ("Greenland", "13:00", 50, "daily"),
            ("St. George", "13:15", 50, "daily"),
            ("Sreekutty", "13:25", 50, "daily"),
            ("Jeeva", "13:40", 50, "daily"),
            ("Jeeva", "14:00", 50, "daily"),
            ("Jeeva", "14:15", 50, "daily"),
            ("Sreelakshmi", "14:35", 50, "daily"),
            ("Jeeva", "14:50", 50, "daily"),
            ("Jeeva", "15:05", 50, "daily"),
            ("Meeras", "15:25", 50, "daily"),
            ("Jeeva", "15:35", 50, "daily"),
            ("KSRTC Kattappana", "15:40", 50, "daily"),
            ("St. George", "15:50", 50, "daily"),
            ("St. George", "16:10", 50, "daily"),
            ("RoseLand", "16:20", 50, "daily"),
            ("Greenland", "16:40", 50, "daily"),
            ("Jeeva", "16:55", 50, "daily"),
            ("Sreekutty", "17:10", 50, "daily"),
            ("Meeras", "17:20", 50, "sunday"),
            ("Sreelakshmi", "17:40", 50, "daily"),
            ("Jeeva", "17:55", 50, "daily"),
            ("Jeeva", "18:10", 50, "daily"),
            ("Meeras", "18:25", 50, "daily"),
            ("Jeeva", "18:40", 50, "daily"),
            ("Jeeva", "18:50", 50, "daily"),
            ("RoseLand", "19:10", 50, "daily"),
            ("St. George", "19:20", 50, "daily"),
            ("Meeras", "19:40", 50, "daily"),
            ("St. George", "20:00", 50, "daily"),
            ("St. George", "20:10", 50, "daily"),
            ("Jeeva", "20:25", 50, "daily"),
            ("Greenland", "20:35", 50, "daily"),
            ("Sreekutty", "21:15", 50, "daily")
        ]

        # Data for Thodupuzha (Towards Thodupuzha)
        thodupuzha_schedules = [
            ("Thodupuzha (Service)", "05:35", 50, "daily"),
            ("Thodupuzha (Service)", "06:45", 50, "daily"),
            ("Thodupuzha (Service)", "07:40", 50, "daily"),
            ("Thodupuzha (Service)", "08:30", 50, "daily"),
            ("Thodupuzha (Service)", "08:50", 50, "daily"),
            ("Thodupuzha (Service)", "09:15", 50, "daily"),
            ("Thodupuzha (Service)", "10:05", 50, "daily"),
            ("Thodupuzha (Service)", "11:05", 50, "daily"),
            ("Thodupuzha (Service)", "12:05", 50, "daily"),
            ("Thodupuzha (Service)", "12:40", 50, "daily"),
            ("Thodupuzha (Service)", "13:15", 50, "daily"),
            ("Thodupuzha (Service)", "14:05", 50, "daily"),
            ("Thodupuzha (Service)", "14:50", 50, "daily"),
            ("Thodupuzha (Service)", "15:15", 50, "daily"),
            ("Thodupuzha (Service)", "15:50", 50, "daily"),
            ("Thodupuzha (Service)", "16:15", 50, "daily"),
            ("Thodupuzha (Service)", "17:05", 50, "daily"),
            ("Thodupuzha (Service)", "17:40", 50, "daily")
        ]

        # Insert schedules
        for bus_name, arr_time, duration, day_type in muvattupuzha_schedules:
            cursor.execute(
                "INSERT INTO schedules (destination_id, bus_id, arrival_time, travel_duration, day_type) VALUES (?, ?, ?, ?, ?)",
                (dest_ids["Muvattupuzha"], bus_ids[bus_name], arr_time, duration, day_type)
            )

        for bus_name, arr_time, duration, day_type in kothamangalam_schedules:
            cursor.execute(
                "INSERT INTO schedules (destination_id, bus_id, arrival_time, travel_duration, day_type) VALUES (?, ?, ?, ?, ?)",
                (dest_ids["Kothamangalam"], bus_ids[bus_name], arr_time, duration, day_type)
            )

        for bus_name, arr_time, duration, day_type in kaliyar_schedules:
            cursor.execute(
                "INSERT INTO schedules (destination_id, bus_id, arrival_time, travel_duration, day_type) VALUES (?, ?, ?, ?, ?)",
                (dest_ids["Kaliyar"], bus_ids[bus_name], arr_time, duration, day_type)
            )

        for bus_name, arr_time, duration, day_type in thodupuzha_schedules:
            cursor.execute(
                "INSERT INTO schedules (destination_id, bus_id, arrival_time, travel_duration, day_type) VALUES (?, ?, ?, ?, ?)",
                (dest_ids["Thodupuzha"], bus_ids[bus_name], arr_time, duration, day_type)
            )
            
        # Data for Njarakkadu (Towards Njarakkadu, coming from different origin points)
        njarakkadu_schedules = [
            ("Jeeva", "07:00", 50, "daily", "Muvattupuzha"),
            ("RoseLand", "08:15", 50, "daily", "Muvattupuzha"),
            ("St. George", "09:30", 50, "daily", "Kothamangalam"),
            ("KSRTC Kattappana", "11:45", 50, "daily", "Kaliyar"),
            ("Meeras", "14:15", 50, "daily", "Thodupuzha"),
            ("Sreelakshmi", "16:30", 50, "daily", "Muvattupuzha"),
            ("Jeeva", "18:45", 50, "daily", "Kaliyar"),
            ("Sreekutty", "20:00", 50, "daily", "Thodupuzha"),
            
            # Thodupuzha -> Njarakkadu
            ("Thodupuzha (Service)", "07:35", 50, "daily", "Thodupuzha"),
            ("Thodupuzha (Service)", "08:30", 50, "daily", "Thodupuzha"),
            ("Thodupuzha (Service)", "09:20", 50, "daily", "Thodupuzha"),
            ("Thodupuzha (Service)", "09:35", 50, "daily", "Thodupuzha"),
            ("Thodupuzha (Service)", "10:00", 50, "daily", "Thodupuzha"),
            ("Thodupuzha (Service)", "11:00", 50, "daily", "Thodupuzha"),
            ("Thodupuzha (Service)", "11:55", 50, "daily", "Thodupuzha"),
            ("Thodupuzha (Service)", "12:25", 50, "daily", "Thodupuzha"),
            ("Thodupuzha (Service)", "12:55", 50, "daily", "Thodupuzha"),
            ("Thodupuzha (Service)", "13:45", 50, "daily", "Thodupuzha"),
            ("Thodupuzha (Service)", "14:10", 50, "daily", "Thodupuzha"),
            ("Thodupuzha (Service)", "15:00", 50, "daily", "Thodupuzha"),
            ("Thodupuzha (Service)", "15:30", 50, "daily", "Thodupuzha"),
            ("Thodupuzha (Service)", "16:15", 50, "daily", "Thodupuzha"),
            ("Thodupuzha (Service)", "16:30", 50, "daily", "Thodupuzha"),
            ("Thodupuzha (Service)", "16:50", 50, "daily", "Thodupuzha"),
            ("Thodupuzha (Service)", "17:55", 50, "daily", "Thodupuzha"),
            ("Thodupuzha (Service)", "18:35", 50, "daily", "Thodupuzha"),
            ("Thodupuzha (Service)", "19:15", 50, "daily", "Thodupuzha")
        ]
        
        for bus_name, arr_time, duration, day_type, from_pt in njarakkadu_schedules:
            cursor.execute(
                "INSERT INTO schedules (destination_id, bus_id, arrival_time, travel_duration, day_type, from_point) VALUES (?, ?, ?, ?, ?, ?)",
                (dest_ids["Njarakkadu"], bus_ids[bus_name], arr_time, duration, day_type, from_pt)
            )
            
        conn.commit()
        logger.info("Database successfully seeded with real bus schedules.")

# --- Database Read Operations ---

def get_destinations() -> List[Dict[str, Any]]:
    """Fetches all destinations from the database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM destinations ORDER BY name ASC")
        return [dict(row) for row in cursor.fetchall()]

def get_destination_by_id(destination_id: int) -> Optional[str]:
    """Retrieves the name of a destination by its ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM destinations WHERE id = ?", (destination_id,))
        row = cursor.fetchone()
        return row["name"] if row else None

def is_date_holiday(date_str: str) -> bool:
    """Checks if the given date (YYYY-MM-DD) is marked as a holiday."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM holidays WHERE holiday_date = ?", (date_str,))
        return cursor.fetchone() is not None

def get_distinct_from_points(destination_id: int) -> List[str]:
    """Fetches distinct starting points (from_point) for a given destination ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT from_point FROM schedules WHERE destination_id = ? ORDER BY from_point ASC",
            (destination_id,)
        )
        return [row["from_point"] for row in cursor.fetchall()]

def get_next_buses(destination_id: int, current_time: str, day_type: str, limit: int = 4, from_point: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Finds the next upcoming buses for a specific destination and day type, handling midnight wrap-around.
    Optionally filters by the starting point (from_point).
    Returns up to 'limit' schedules.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Select all schedules that match the destination and day type (including daily)
        query = """
            SELECT s.id as schedule_id, s.arrival_time, s.travel_duration, s.day_type, s.from_point,
                   b.name as bus_name, b.type as bus_type, d.name as destination_name
            FROM schedules s
            JOIN buses b ON s.bus_id = b.id
            JOIN destinations d ON s.destination_id = d.id
            WHERE s.destination_id = ?
              AND (s.day_type = 'daily' OR s.day_type = ?)
        """
        params = [destination_id, day_type]
        if from_point:
            query += " AND s.from_point = ?"
            params.append(from_point)
            
        query += " ORDER BY s.arrival_time ASC"
        
        cursor.execute(query, params)
        schedules = [dict(row) for row in cursor.fetchall()]
        if not schedules:
            return []
            
        # Segment into buses after current_time and buses before current_time (next day)
        after_now = [s for s in schedules if s["arrival_time"] >= current_time]
        before_now = [s for s in schedules if s["arrival_time"] < current_time]
        
        # Combine lists to handle wrap-around: first everything remaining today, then early tomorrow
        combined = after_now + before_now
        return combined[:limit]

def get_schedule_details(schedule_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves detailed information for a specific schedule by ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.id as schedule_id, s.arrival_time, s.travel_duration, s.day_type, s.from_point,
                   b.name as bus_name, b.type as bus_type, d.name as destination_name, s.bus_id, s.destination_id
            FROM schedules s
            JOIN buses b ON s.bus_id = b.id
            JOIN destinations d ON s.destination_id = d.id
            WHERE s.id = ?
        """, (schedule_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

# --- Database Write/Admin Operations ---

def add_bus(name: str, bus_type: str) -> int:
    """Inserts a new bus or retrieves its ID if it already exists."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM buses WHERE name = ?", (name,))
        row = cursor.fetchone()
        if row:
            # Update type if it changed
            cursor.execute("UPDATE buses SET type = ? WHERE id = ?", (bus_type, row["id"]))
            conn.commit()
            return row["id"]
        
        cursor.execute("INSERT INTO buses (name, type) VALUES (?, ?)", (name, bus_type))
        conn.commit()
        return cursor.lastrowid

def get_buses() -> List[Dict[str, Any]]:
    """Fetches all registered buses."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, type FROM buses ORDER BY name ASC")
        return [dict(row) for row in cursor.fetchall()]

def add_schedule(destination_id: int, bus_id: int, arrival_time: str, travel_duration: int, day_type: str, from_point: str = 'Njarakkadu') -> int:
    """Adds a new schedule/timetable entry to the database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO schedules (destination_id, bus_id, arrival_time, travel_duration, day_type, from_point)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (destination_id, bus_id, arrival_time, travel_duration, day_type, from_point))
        conn.commit()
        return cursor.lastrowid

def update_schedule(schedule_id: int, arrival_time: str, travel_duration: int, day_type: str, from_point: str, bus_id: Optional[int] = None) -> bool:
    """Updates timetable entry timings, metadata, and optionally the bus ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if bus_id is not None:
            cursor.execute("""
                UPDATE schedules
                SET arrival_time = ?, travel_duration = ?, day_type = ?, from_point = ?, bus_id = ?
                WHERE id = ?
            """, (arrival_time, travel_duration, day_type, from_point, bus_id, schedule_id))
        else:
            cursor.execute("""
                UPDATE schedules
                SET arrival_time = ?, travel_duration = ?, day_type = ?, from_point = ?
                WHERE id = ?
            """, (arrival_time, travel_duration, day_type, from_point, schedule_id))
        conn.commit()
        return cursor.rowcount > 0


def delete_schedule(schedule_id: int) -> bool:
    """Deletes a schedule entry by its ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
        conn.commit()
        return cursor.rowcount > 0

def delete_bus_schedules(bus_id: int) -> bool:
    """Deletes all schedules associated with a specific bus."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM schedules WHERE bus_id = ?", (bus_id,))
        conn.commit()
        return cursor.rowcount > 0

def delete_bus(bus_id: int) -> bool:
    """Deletes a bus and all its associated schedules (cascading)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Due to ON DELETE CASCADE on foreign keys, deleting a bus will delete schedules
        cursor.execute("DELETE FROM buses WHERE id = ?", (bus_id,))
        conn.commit()
        return cursor.rowcount > 0

def get_all_schedules() -> List[Dict[str, Any]]:
    """Retrieves all schedules sorted by destination name and arrival time."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.id as schedule_id, s.arrival_time, s.travel_duration, s.day_type, s.from_point,
                   b.name as bus_name, b.type as bus_type, d.name as destination_name, s.bus_id
            FROM schedules s
            JOIN buses b ON s.bus_id = b.id
            JOIN destinations d ON s.destination_id = d.id
            ORDER BY d.name ASC, s.arrival_time ASC
        """)
        return [dict(row) for row in cursor.fetchall()]

def get_schedules_by_destination(destination_id: int) -> List[Dict[str, Any]]:
    """Retrieves schedules for a specific destination."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.id as schedule_id, s.arrival_time, s.travel_duration, s.day_type, s.from_point,
                   b.name as bus_name, b.type as bus_type, d.name as destination_name, s.bus_id
            FROM schedules s
            JOIN buses b ON s.bus_id = b.id
            JOIN destinations d ON s.destination_id = d.id
            WHERE s.destination_id = ?
            ORDER BY s.arrival_time ASC
        """, (destination_id,))
        return [dict(row) for row in cursor.fetchall()]

def get_schedules_for_day(destination_id: int, day_type: str, from_point: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetches all schedules for a destination and day type (including daily), sorted by arrival_time."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        query = """
            SELECT s.id as schedule_id, s.arrival_time, s.travel_duration, s.day_type, s.from_point,
                   b.name as bus_name, b.type as bus_type, d.name as destination_name, s.bus_id, s.destination_id
            FROM schedules s
            JOIN buses b ON s.bus_id = b.id
            JOIN destinations d ON s.destination_id = d.id
            WHERE s.destination_id = ?
              AND (s.day_type = 'daily' OR s.day_type = ?)
        """
        params = [destination_id, day_type]
        if from_point:
            query += " AND s.from_point = ?"
            params.append(from_point)
            
        query += " ORDER BY s.arrival_time ASC"
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

# --- Holiday Operations ---

def add_holiday(holiday_date: str) -> int:
    """Adds a new holiday date (YYYY-MM-DD)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO holidays (holiday_date) VALUES (?)", (holiday_date,))
        conn.commit()
        return cursor.lastrowid

def delete_holiday(holiday_date: str) -> bool:
    """Deletes a holiday date (YYYY-MM-DD)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM holidays WHERE holiday_date = ?", (holiday_date,))
        conn.commit()
        return cursor.rowcount > 0

def get_all_holidays() -> List[str]:
    """Retrieves all holiday dates."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT holiday_date FROM holidays ORDER BY holiday_date ASC")
        return [row["holiday_date"] for row in cursor.fetchall()]
