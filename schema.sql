-- Schema for Engotta Bus Timetable Database

CREATE TABLE IF NOT EXISTS destinations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS buses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL CHECK(type IN ('KSRTC', 'Private'))
);

CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    destination_id INTEGER NOT NULL,
    bus_id INTEGER NOT NULL,
    arrival_time TEXT NOT NULL, -- Format: HH:MM (24-hour style, e.g., '14:30')
    travel_duration INTEGER NOT NULL, -- Format: duration in minutes (e.g., 45)
    day_type TEXT NOT NULL CHECK(day_type IN ('daily', 'weekday', 'sunday', 'holiday')),
    from_point TEXT NOT NULL DEFAULT 'Njarakkadu',
    FOREIGN KEY (destination_id) REFERENCES destinations(id) ON DELETE CASCADE,
    FOREIGN KEY (bus_id) REFERENCES buses(id) ON DELETE CASCADE,
    UNIQUE(destination_id, bus_id, arrival_time, day_type) -- Avoid duplicate schedules
);

CREATE TABLE IF NOT EXISTS holidays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    holiday_date TEXT NOT NULL UNIQUE -- Format: YYYY-MM-DD
);

CREATE TABLE IF NOT EXISTS migrations (
    name TEXT PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

