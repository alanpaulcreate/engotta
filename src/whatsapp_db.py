import sqlite3
import json
from typing import Dict, Any, Optional
from src.db import get_db_connection
from src.config import logger

def init_whatsapp_db() -> None:
    """Initializes the whatsapp_sessions table in the database."""
    logger.info("Initializing WhatsApp session database table...")
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS whatsapp_sessions (
                phone_number TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                context_data TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

def get_whatsapp_session(phone_number: str) -> Optional[Dict[str, Any]]:
    """Retrieves session state and parsed context data for a given phone number."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT state, context_data FROM whatsapp_sessions WHERE phone_number = ?",
            (phone_number,)
        )
        row = cursor.fetchone()
        if row:
            state = row["state"]
            context_data = {}
            if row["context_data"]:
                try:
                    context_data = json.loads(row["context_data"])
                except Exception as e:
                    logger.error(f"Error parsing session context JSON for {phone_number}: {e}")
            return {"state": state, "context_data": context_data}
        return None

def save_whatsapp_session(phone_number: str, state: str, context_data: Dict[str, Any]) -> None:
    """Saves or updates the session state and context data for a given phone number."""
    context_str = json.dumps(context_data)
    with get_db_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO whatsapp_sessions (phone_number, state, context_data, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (phone_number, state, context_str))
        conn.commit()

def delete_whatsapp_session(phone_number: str) -> None:
    """Clears/deletes the session for a given phone number."""
    with get_db_connection() as conn:
        conn.execute("DELETE FROM whatsapp_sessions WHERE phone_number = ?", (phone_number,))
        conn.commit()
