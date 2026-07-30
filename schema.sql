-- ============================================================
-- Engotta Bus Timetable Database Schema (PostgreSQL / BCNF)
-- ============================================================
-- BCNF guarantee: For every non-trivial functional dependency
-- X -> Y in each table, X is a superkey.
-- ============================================================

-- All physical locations (origins AND destinations)
CREATE TABLE IF NOT EXISTS places (
    id   SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

-- Bus vehicles (name not unique — multiple buses can share a name)
CREATE TABLE IF NOT EXISTS buses (
    id   SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('KSRTC', 'Private'))
);

-- Routes: an ordered pair of places with a fixed travel duration.
-- BCNF: (origin_id, destination_id) is a candidate key -> travel_duration.
CREATE TABLE IF NOT EXISTS routes (
    id              SERIAL PRIMARY KEY,
    origin_id       INTEGER NOT NULL REFERENCES places (id) ON DELETE CASCADE,
    destination_id  INTEGER NOT NULL REFERENCES places (id) ON DELETE CASCADE,
    travel_duration INTEGER NOT NULL,   -- minutes
    UNIQUE (origin_id, destination_id)
);

-- Schedules: a bus departs on a route at a given time on a given day type.
-- BCNF: (bus_id, route_id, arrival_time, day_type) is the candidate key.
CREATE TABLE IF NOT EXISTS schedules (
    id           SERIAL PRIMARY KEY,
    bus_id       INTEGER NOT NULL REFERENCES buses  (id) ON DELETE CASCADE,
    route_id     INTEGER NOT NULL REFERENCES routes (id) ON DELETE CASCADE,
    arrival_time TEXT    NOT NULL,  -- HH:MM (24-hour)
    day_type     TEXT    NOT NULL CHECK (day_type IN ('daily', 'weekday', 'sunday', 'holiday')),
    UNIQUE (bus_id, route_id, arrival_time, day_type)
);

-- Public holidays (overrides the normal day_type to 'holiday')
CREATE TABLE IF NOT EXISTS holidays (
    id           SERIAL PRIMARY KEY,
    holiday_date DATE NOT NULL UNIQUE  -- YYYY-MM-DD
);

-- WhatsApp user sessions (previously in a separate SQLite file)
CREATE TABLE IF NOT EXISTS whatsapp_sessions (
    phone_number TEXT        PRIMARY KEY,
    state        TEXT        NOT NULL,
    context_data TEXT        NOT NULL DEFAULT '{}',
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
