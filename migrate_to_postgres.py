"""
migrate_to_postgres.py
----------------------
One-time migration script:
  1. Reads all data from the local SQLite database.
  2. Applies the new BCNF schema to the Neon PostgreSQL database.
  3. Inserts all places, buses, routes, and schedules.

Run with:
    venv\Scripts\python.exe migrate_to_postgres.py
"""

import sqlite3
import os
import psycopg2
import psycopg2.extras
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

SQLITE_PATH = Path("data/database.db")
PG_URL = os.getenv("DATABASE_URL")

if not PG_URL:
    raise RuntimeError("DATABASE_URL is not set in .env!")

# ── 1. Read from SQLite ────────────────────────────────────────────────────
print("Reading SQLite data...")
sq = sqlite3.connect(SQLITE_PATH)
sq.row_factory = sqlite3.Row

destinations = [dict(r) for r in sq.execute("SELECT * FROM destinations")]
buses        = [dict(r) for r in sq.execute("SELECT * FROM buses")]
holidays     = [dict(r) for r in sq.execute("SELECT * FROM holidays")]
schedules_raw = [dict(r) for r in sq.execute("""
    SELECT s.id, s.arrival_time, s.travel_duration, s.day_type,
           s.from_point,
           b.name  AS bus_name,
           b.type  AS bus_type,
           d.name  AS dest_name
    FROM   schedules s
    JOIN   buses       b ON b.id = s.bus_id
    JOIN   destinations d ON d.id = s.destination_id
""")]
sq.close()

print(f"  Found {len(destinations)} destinations, {len(buses)} buses, {len(schedules_raw)} schedules, {len(holidays)} holidays")

# ── 2. Connect to PostgreSQL ───────────────────────────────────────────────
print("\nConnecting to PostgreSQL...")
pg = psycopg2.connect(PG_URL)
cur = pg.cursor()

# Apply schema
print("Applying schema...")
with open("schema.sql") as f:
    cur.execute(f.read())
pg.commit()
print("  Schema applied.")

# ── 3. Insert places (union of destinations + from_points) ─────────────────
all_place_names = set(d["name"] for d in destinations)
all_place_names.update(s["from_point"] for s in schedules_raw)

print(f"\nInserting {len(all_place_names)} places: {sorted(all_place_names)}")
for name in sorted(all_place_names):
    cur.execute(
        "INSERT INTO places (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
        (name,)
    )
pg.commit()

# Build place name -> id map
cur.execute("SELECT id, name FROM places")
place_map = {row[1]: row[0] for row in cur.fetchall()}
print(f"  Place map: {place_map}")

# ── 4. Insert buses ────────────────────────────────────────────────────────
print(f"\nInserting {len(buses)} buses...")
# Bus name is NOT unique — use original ids to build a map
bus_old_to_new = {}
for b in buses:
    cur.execute(
        "INSERT INTO buses (name, type) VALUES (%s, %s) RETURNING id",
        (b["name"], b["type"])
    )
    new_id = cur.fetchone()[0]
    bus_old_to_new[b["id"]] = new_id
pg.commit()
print(f"  Bus old->new id map: {bus_old_to_new}")

# Rebuild bus name->new_id for schedule migration
# (use the first inserted id when names repeat)
bus_name_to_new_id = {}
cur.execute("SELECT id, name FROM buses ORDER BY id")
for row in cur.fetchall():
    if row[1] not in bus_name_to_new_id:
        bus_name_to_new_id[row[1]] = row[0]

# ── 5. Insert routes ───────────────────────────────────────────────────────
# A route = (from_point -> dest_name) with a travel_duration.
# The same origin/destination pair always has the same duration in the data.
routes_seen = {}
for s in schedules_raw:
    key = (s["from_point"], s["dest_name"])
    if key not in routes_seen:
        routes_seen[key] = s["travel_duration"]

print(f"\nInserting {len(routes_seen)} routes...")
route_map = {}
for (origin_name, dest_name), duration in routes_seen.items():
    origin_id = place_map[origin_name]
    dest_id   = place_map[dest_name]
    cur.execute("""
        INSERT INTO routes (origin_id, destination_id, travel_duration)
        VALUES (%s, %s, %s)
        ON CONFLICT (origin_id, destination_id) DO UPDATE
            SET travel_duration = EXCLUDED.travel_duration
        RETURNING id
    """, (origin_id, dest_id, duration))
    route_id = cur.fetchone()[0]
    route_map[(origin_name, dest_name)] = route_id
    print(f"  Route: {origin_name} -> {dest_name} ({duration} min) = id {route_id}")
pg.commit()

# ── 6. Insert schedules ────────────────────────────────────────────────────
print(f"\nInserting {len(schedules_raw)} schedules...")
inserted = 0
skipped  = 0
for s in schedules_raw:
    bus_id   = bus_name_to_new_id.get(s["bus_name"])
    route_id = route_map.get((s["from_point"], s["dest_name"]))
    if not bus_id or not route_id:
        print(f"  SKIP (missing bus/route): {s}")
        skipped += 1
        continue
    cur.execute("""
        INSERT INTO schedules (bus_id, route_id, arrival_time, day_type)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT DO NOTHING
    """, (bus_id, route_id, s["arrival_time"], s["day_type"]))
    inserted += 1
pg.commit()
print(f"  Inserted: {inserted}, Skipped: {skipped}")

# ── 7. Insert holidays ─────────────────────────────────────────────────────
if holidays:
    print(f"\nInserting {len(holidays)} holidays...")
    for h in holidays:
        cur.execute(
            "INSERT INTO holidays (holiday_date) VALUES (%s) ON CONFLICT DO NOTHING",
            (h["holiday_date"],)
        )
    pg.commit()
else:
    print("\nNo holidays to migrate.")

# ── Done ───────────────────────────────────────────────────────────────────
cur.close()
pg.close()
print("\n✅ Migration complete! All data is now in PostgreSQL.")
