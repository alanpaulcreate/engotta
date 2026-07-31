"""
src/db.py  –  PostgreSQL (psycopg2) version
All queries use the normalized BCNF schema:
  places, buses, routes, schedules, holidays
"""

import os
import psycopg2
import psycopg2.extras
from typing import List, Dict, Any, Optional
from src.config import logger

# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def get_db_connection() -> psycopg2.extensions.connection:
    """Returns a psycopg2 connection with DictCursor row factory."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set!")
    conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


def init_db(schema_path: str = "schema.sql") -> None:
    """Applies the schema (idempotent – all tables use CREATE IF NOT EXISTS)."""
    logger.info("Initializing PostgreSQL database schema...")
    if not os.path.exists(schema_path):
        logger.error(f"Schema file not found at: {schema_path}")
        return
    with open(schema_path, "r") as f:
        schema_sql = f.read()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()
    logger.info("PostgreSQL schema applied successfully.")


# ---------------------------------------------------------------------------
# Destination helpers (destinations are now 'places' that are the target of
# at least one route, i.e. destination_id appears in routes).
# We keep the same public API so no callers need changing.
# ---------------------------------------------------------------------------

def get_destinations() -> List[Dict[str, Any]]:
    """Returns all places that appear as a destination in at least one route."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT p.id, p.name
                FROM   places p
                JOIN   routes r ON r.destination_id = p.id
                ORDER  BY p.name ASC
            """)
            return [dict(row) for row in cur.fetchall()]


def get_destination_by_id(destination_id: int) -> Optional[str]:
    """Returns the name of a place by its ID."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM places WHERE id = %s", (destination_id,))
            row = cur.fetchone()
            return row["name"] if row else None


# ---------------------------------------------------------------------------
# Places
# ---------------------------------------------------------------------------

def get_all_places() -> List[Dict[str, Any]]:
    """Returns every place in the places table."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name FROM places ORDER BY name ASC")
            return [dict(row) for row in cur.fetchall()]


def get_place_by_name(name: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name FROM places WHERE LOWER(name) = LOWER(%s)", (name,))
            row = cur.fetchone()
            return dict(row) if row else None


# ---------------------------------------------------------------------------
# Distinct origin points for a given destination
# ---------------------------------------------------------------------------

def get_distinct_from_points(destination_id: int) -> List[str]:
    """
    Returns distinct origin place names that have a route leading to destination_id.
    Replaces the old 'from_point' TEXT column query.
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT p.name
                FROM   routes r
                JOIN   places  p ON p.id = r.origin_id
                WHERE  r.destination_id = %s
                ORDER  BY p.name ASC
            """, (destination_id,))
            return [row["name"] for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Bus queries
# ---------------------------------------------------------------------------

def get_buses() -> List[Dict[str, Any]]:
    """Fetches all registered buses."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, type FROM buses ORDER BY name ASC")
            return [dict(row) for row in cur.fetchall()]


def add_bus(name: str, bus_type: str) -> int:
    """Inserts a new bus. Bus names are NOT unique; always inserts a new row."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO buses (name, type) VALUES (%s, %s) RETURNING id",
                (name, bus_type)
            )
            new_id = cur.fetchone()["id"]
        conn.commit()
    return new_id


# ---------------------------------------------------------------------------
# Route helpers (internal – used by schedule functions)
# ---------------------------------------------------------------------------

def _get_or_create_route(conn, origin_name: str, destination_name: str, travel_duration: int) -> int:
    """Gets or creates a route between two place names. Returns route id."""
    with conn.cursor() as cur:
        # Ensure both places exist
        for place in (origin_name, destination_name):
            cur.execute(
                "INSERT INTO places (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
                (place,)
            )

        # Look up IDs
        cur.execute("SELECT id FROM places WHERE name = %s", (origin_name,))
        origin_id = cur.fetchone()["id"]
        cur.execute("SELECT id FROM places WHERE name = %s", (destination_name,))
        dest_id = cur.fetchone()["id"]

        # Get or create route
        cur.execute(
            "SELECT id FROM routes WHERE origin_id = %s AND destination_id = %s",
            (origin_id, dest_id)
        )
        row = cur.fetchone()
        if row:
            return row["id"]

        cur.execute("""
            INSERT INTO routes (origin_id, destination_id, travel_duration)
            VALUES (%s, %s, %s) RETURNING id
        """, (origin_id, dest_id, travel_duration))
        return cur.fetchone()["id"]


# ---------------------------------------------------------------------------
# Schedule read operations
# ---------------------------------------------------------------------------

def get_next_buses(
    destination_id: int,
    current_time: str,
    day_type: str,
    limit: int = 4,
    from_point: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Returns the next `limit` buses heading to destination_id.
    Handles midnight wrap-around. Optionally filters by origin place name.
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            query = """
                SELECT s.id             AS schedule_id,
                       s.arrival_time,
                       r.travel_duration,
                       s.day_type,
                       op.name          AS from_point,
                       b.name           AS bus_name,
                       b.type           AS bus_type,
                       dp.name          AS destination_name
                FROM   schedules s
                JOIN   buses  b  ON b.id  = s.bus_id
                JOIN   routes r  ON r.id  = s.route_id
                JOIN   places op ON op.id = r.origin_id
                JOIN   places dp ON dp.id = r.destination_id
                WHERE  r.destination_id = %s
                  AND  (s.day_type = 'daily' OR s.day_type = %s)
            """
            params: List[Any] = [destination_id, day_type]

            if from_point:
                query += " AND op.name = %s"
                params.append(from_point)

            query += " ORDER BY s.arrival_time ASC"
            cur.execute(query, params)
            schedules = [dict(row) for row in cur.fetchall()]

    if not schedules:
        return []

    after_now  = [s for s in schedules if s["arrival_time"] >= current_time]
    before_now = [s for s in schedules if s["arrival_time"] <  current_time]
    return (after_now + before_now)[:limit]


def get_schedules_for_day(
    destination_id: int,
    day_type: str,
    from_point: Optional[str] = None
) -> List[Dict[str, Any]]:
    """All schedules for a destination & day type, sorted by arrival_time."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            query = """
                SELECT s.id             AS schedule_id,
                       s.arrival_time,
                       r.travel_duration,
                       s.day_type,
                       op.name          AS from_point,
                       b.name           AS bus_name,
                       b.type           AS bus_type,
                       dp.name          AS destination_name,
                       s.bus_id,
                       r.destination_id
                FROM   schedules s
                JOIN   buses  b  ON b.id  = s.bus_id
                JOIN   routes r  ON r.id  = s.route_id
                JOIN   places op ON op.id = r.origin_id
                JOIN   places dp ON dp.id = r.destination_id
                WHERE  r.destination_id = %s
                  AND  (s.day_type = 'daily' OR s.day_type = %s)
            """
            params: List[Any] = [destination_id, day_type]

            if from_point:
                query += " AND op.name = %s"
                params.append(from_point)

            query += " ORDER BY s.arrival_time ASC"
            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]


def get_schedule_details(schedule_id: int) -> Optional[Dict[str, Any]]:
    """Full details for one schedule entry."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT s.id             AS schedule_id,
                       s.arrival_time,
                       r.travel_duration,
                       s.day_type,
                       op.name          AS from_point,
                       b.name           AS bus_name,
                       b.type           AS bus_type,
                       dp.name          AS destination_name,
                       s.bus_id,
                       r.destination_id
                FROM   schedules s
                JOIN   buses  b  ON b.id  = s.bus_id
                JOIN   routes r  ON r.id  = s.route_id
                JOIN   places op ON op.id = r.origin_id
                JOIN   places dp ON dp.id = r.destination_id
                WHERE  s.id = %s
            """, (schedule_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def get_all_schedules() -> List[Dict[str, Any]]:
    """All schedules, sorted by destination name then arrival time."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT s.id             AS schedule_id,
                       s.arrival_time,
                       r.travel_duration,
                       s.day_type,
                       op.name          AS from_point,
                       b.name           AS bus_name,
                       b.type           AS bus_type,
                       dp.name          AS destination_name,
                       s.bus_id,
                       r.destination_id AS destination_id
                FROM   schedules s
                JOIN   buses  b  ON b.id  = s.bus_id
                JOIN   routes r  ON r.id  = s.route_id
                JOIN   places op ON op.id = r.origin_id
                JOIN   places dp ON dp.id = r.destination_id
                ORDER  BY dp.name ASC, s.arrival_time ASC
            """)
            return [dict(row) for row in cur.fetchall()]


def get_schedules_by_destination(destination_id: int) -> List[Dict[str, Any]]:
    """All schedules for a specific destination."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT s.id             AS schedule_id,
                       s.arrival_time,
                       r.travel_duration,
                       s.day_type,
                       op.name          AS from_point,
                       b.name           AS bus_name,
                       b.type           AS bus_type,
                       dp.name          AS destination_name,
                       s.bus_id
                FROM   schedules s
                JOIN   buses  b  ON b.id  = s.bus_id
                JOIN   routes r  ON r.id  = s.route_id
                JOIN   places op ON op.id = r.origin_id
                JOIN   places dp ON dp.id = r.destination_id
                WHERE  r.destination_id = %s
                ORDER  BY s.arrival_time ASC
            """, (destination_id,))
            return [dict(row) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Schedule write/admin operations
# ---------------------------------------------------------------------------

def add_schedule(
    destination_id: int,
    bus_id: int,
    arrival_time: str,
    travel_duration: int,
    day_type: str,
    from_point: str = "Njarakkadu"
) -> int:
    """
    Adds a new schedule. Automatically resolves / creates the route between
    from_point (origin) and the destination identified by destination_id.
    """
    with get_db_connection() as conn:
        # Resolve destination name
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM places WHERE id = %s", (destination_id,))
            dest_row = cur.fetchone()
            if not dest_row:
                raise ValueError(f"Destination id {destination_id} not found in places table.")
            dest_name = dest_row["name"]

        route_id = _get_or_create_route(conn, from_point, dest_name, travel_duration)

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO schedules (bus_id, route_id, arrival_time, day_type)
                VALUES (%s, %s, %s, %s) RETURNING id
            """, (bus_id, route_id, arrival_time, day_type))
            new_id = cur.fetchone()["id"]
        conn.commit()
    return new_id


def update_schedule(
    schedule_id: int,
    arrival_time: str,
    travel_duration: int,
    day_type: str,
    from_point: str,
    bus_id: Optional[int] = None
) -> bool:
    """Updates a schedule's time, day_type, and optionally bus_id / route."""
    with get_db_connection() as conn:
        # Get current schedule to find destination
        with conn.cursor() as cur:
            cur.execute("""
                SELECT s.bus_id, r.destination_id, dp.name AS dest_name
                FROM   schedules s
                JOIN   routes r  ON r.id  = s.route_id
                JOIN   places dp ON dp.id = r.destination_id
                WHERE  s.id = %s
            """, (schedule_id,))
            row = cur.fetchone()
            if not row:
                return False
            effective_bus_id = bus_id if bus_id is not None else row["bus_id"]
            dest_name = row["dest_name"]

        route_id = _get_or_create_route(conn, from_point, dest_name, travel_duration)

        with conn.cursor() as cur:
            cur.execute("""
                UPDATE schedules
                SET    bus_id = %s, route_id = %s, arrival_time = %s, day_type = %s
                WHERE  id = %s
            """, (effective_bus_id, route_id, arrival_time, day_type, schedule_id))
            affected = cur.rowcount
        conn.commit()
    return affected > 0


def delete_schedule(schedule_id: int) -> bool:
    """Deletes a schedule by ID."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM schedules WHERE id = %s", (schedule_id,))
            affected = cur.rowcount
        conn.commit()
    return affected > 0


def delete_bus(bus_id: int) -> bool:
    """Deletes a bus (cascades to schedules via FK)."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM buses WHERE id = %s", (bus_id,))
            affected = cur.rowcount
        conn.commit()
    return affected > 0


def delete_bus_schedules(bus_id: int) -> bool:
    """Deletes all schedules for a given bus."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM schedules WHERE bus_id = %s", (bus_id,))
            affected = cur.rowcount
        conn.commit()
    return affected > 0


# ---------------------------------------------------------------------------
# Holiday operations
# ---------------------------------------------------------------------------

def is_date_holiday(date_str: str) -> bool:
    """Checks whether date_str (YYYY-MM-DD) is a holiday."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM holidays WHERE holiday_date = %s", (date_str,))
            return cur.fetchone() is not None


def add_holiday(holiday_date: str) -> int:
    """Adds a holiday date. Silently ignores duplicates."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO holidays (holiday_date) VALUES (%s)
                ON CONFLICT (holiday_date) DO NOTHING
                RETURNING id
            """, (holiday_date,))
            row = cur.fetchone()
        conn.commit()
    return row["id"] if row else -1


def delete_holiday(holiday_date: str) -> bool:
    """Deletes a holiday date."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM holidays WHERE holiday_date = %s", (holiday_date,))
            affected = cur.rowcount
        conn.commit()
    return affected > 0


def get_all_holidays() -> List[str]:
    """Returns all holiday dates as strings."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT holiday_date::text FROM holidays ORDER BY holiday_date ASC")
            return [row["holiday_date"] for row in cur.fetchall()]


def get_schedules_by_bus_name_search(
    bus_name: str, day_type: str, current_time: str
) -> List[Dict[str, Any]]:
    """Retrieves upcoming schedules for buses whose name partially matches bus_name.

    Matches are case-insensitive (ILIKE). Results include 'daily' schedules and
    schedules specific to the given day_type, filtered to arrival_time >= current_time.
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    s.id            AS schedule_id,
                    s.arrival_time::text  AS arrival_time,
                    s.travel_duration,
                    s.day_type,
                    s.from_point,
                    b.name          AS bus_name,
                    b.type          AS bus_type,
                    d.name          AS destination_name
                FROM schedules s
                JOIN buses b ON s.bus_id = b.id
                JOIN destinations d ON s.destination_id = d.id
                WHERE b.name ILIKE %s
                  AND s.day_type IN ('daily', %s)
                  AND s.arrival_time::text >= %s
                ORDER BY s.arrival_time ASC
                """,
                (f"%{bus_name}%", day_type, current_time),
            )
            return [dict(row) for row in cur.fetchall()]
