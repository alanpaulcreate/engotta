# Engotta - Bus Timetable Telegram Bot

Engotta is a timetable-based Telegram bot designed to answer one crucial question: **"Which bus can I catch right now?"** 

It provides users standing at bus stops with instant access to:
- Next available bus for their destination.
- Waiting time (with midnight wrap-around support).
- Next 3 upcoming buses.
- Destination and journey duration details.
- "Available Now" view showing the next bus for all destinations at the current moment.
- External link to [Veyil](https://veyil.app).

---

## 🛠️ Tech Stack

- **Language:** Python 3.9+
- **Telegram Bot Library:** `python-telegram-bot` (v20.x, Async-based)
- **Database:** SQLite
- **Timezone Management:** `pytz`

---

## 📂 Project Structure

```
engotta/
│
├── data/                     # Data directory (created at runtime for DB storage)
│
├── src/
│   ├── __init__.py           # Package marker
│   ├── config.py             # Config parser for env variables & logging
│   ├── db.py                 # SQLite CRUD, migration, and auto-seeding logic
│   ├── bot.py                # Bot runner & handler registry
│   │
│   ├── handlers/             # Application event handlers
│   │   ├── __init__.py
│   │   ├── user.py           # User-facing commands & query buttons
│   │   └── admin.py          # Admin conversation Wizards (/addbus, /editbus, etc.)
│   │
│   └── utils/                # Utility helpers
│       ├── __init__.py
│       └── time_helper.py    # Timetable math, formatters, and day calculators
│
├── .env.example              # Env variables template
├── .gitignore                # Files to ignore in git
├── Dockerfile                # Production Docker configuration
├── Procfile                  # Process file for Render/Railway deployment
├── requirements.txt          # Python dependencies
├── schema.sql                # SQL database schema
└── README.md                 # Project documentation (this file)
```

---

## 🚀 Setup & Installation

### Local Installation

1. **Clone the repository:**
   ```bash
   git clone <repo-url>
   cd engotta
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and fill in:
   - `TELEGRAM_BOT_TOKEN`: Obtain from [@BotFather](https://t.me/BotFather) on Telegram.
   - `ADMIN_IDS`: Comma-separated list of Telegram User IDs allowed to perform admin actions (e.g. `123456789`). Use [@userinfobot](https://t.me/userinfobot) to find your ID.
   - `TIMEZONE`: The local timezone for timetable calculation (defaults to `Asia/Kolkata` for India/Kerala).

5. **Run the bot:**
   ```bash
   python -m src.bot
   ```
   *Note: On first startup, the database is automatically created, the schema is applied, and default bus data is seeded.*

---

## 💾 Database Schema

The database consists of 4 main tables:
1. **`destinations`**: Keeps track of stops (seeding includes *Muvattupuzha*, *Kaliyar*, *Kothamangalam*, *Thodupuzha*, *Njarakkadu*).
2. **`buses`**: Contains registered bus info and types (`KSRTC` or `Private`).
3. **`schedules`**: Houses the actual timetable schedules.
   - `arrival_time`: Stored in 24h `HH:MM` format.
   - `travel_duration`: Duration in minutes.
   - `day_type`: Active schedule filter (`daily`, `weekday`, `sunday`, `holiday`).
4. **`holidays`**: Stores holiday calendar dates (`YYYY-MM-DD`). If today's date matches a row here, only `holiday` and `daily` schedule rules are active.

---

## 👥 Bot Commands

### User Commands
- `/start` - Displays the main interactive inline keyboard with destinations, a link to Veyil, and the "Available Now" dashboard.

### Admin Commands (Restricted to `ADMIN_IDS`)
- `/listschedules` - Displays a detailed view of all configured bus schedules grouped by destination.
- `/addbus` - Starts a 6-step guided wizard to add a new schedule entry.
- `/editbus` - Starts a wizard to edit existing schedule fields (Arrival Time, Duration, Day Type).
- `/deletebus` - Starts a wizard to delete a schedule from the database with confirmation prompt.
- `/addholiday <YYYY-MM-DD>` - Adds a holiday date to the database (e.g. `/addholiday 2026-08-15`).
- `/deleteholiday <YYYY-MM-DD>` - Deletes a holiday date from the database.
- `/listholidays` - Lists all registered holidays.

---

## ☁️ Deployment

This project is ready for deployment on **Render** or **Railway**.

### Option A: Railway
1. Create a new project on Railway.
2. Select **Deploy from GitHub repo**.
3. In **Variables**, add the following:
   - `TELEGRAM_BOT_TOKEN`
   - `ADMIN_IDS`
   - `DATABASE_PATH` = `data/database.db`
   - `TIMEZONE` = `Asia/Kolkata`
4. Set up a **Volume** mounted at `/app/data` to persist your SQLite database across deployments.
5. Railway will read the `Dockerfile` automatically and spin up the bot worker.

### Option B: Render
1. Create a new **Background Worker** service on Render.
2. Link your GitHub repository.
3. In the environment setup, configure your environment variables (`TELEGRAM_BOT_TOKEN`, `ADMIN_IDS`, `DATABASE_PATH`, `TIMEZONE`).
4. Set up a **Disk** mount to persist the SQLite file:
   - **Mount Path:** `/app/data`
   - **Size:** `1 GiB` (more than enough for SQLite)
5. Render will run the dockerized worker, establishing persistent connection with Telegram's servers.
