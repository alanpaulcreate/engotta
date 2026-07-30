"""
src/whatsapp_db.py  –  PostgreSQL (psycopg2) version
Manages WhatsApp user sessions stored in the 'whatsapp_sessions' table.
"""

import json
import os
import psycopg2
import psycopg2.extras
from typing import Optional, Dict, Any
from src.config import logger


def _get_conn() -> psycopg2.extensions.connection:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set!")
    return psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)


def init_whatsapp_db() -> None:
    """Creates the whatsapp_sessions table if it does not already exist."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS whatsapp_sessions (
                    phone_number TEXT        PRIMARY KEY,
                    state        TEXT        NOT NULL,
                    context_data TEXT        NOT NULL DEFAULT '{}',
                    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
        conn.commit()
    logger.info("WhatsApp sessions table is ready (PostgreSQL).")


def get_whatsapp_session(phone_number: str) -> Optional[Dict[str, Any]]:
    """Returns the session dict for a phone number, or None if not found."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT state, context_data FROM whatsapp_sessions WHERE phone_number = %s",
                (phone_number,)
            )
            row = cur.fetchone()
    if not row:
        return None
    context = row["context_data"]
    if isinstance(context, str):
        context = json.loads(context)
    return {"state": row["state"], "context_data": context}


def save_whatsapp_session(phone_number: str, state: str, context_data: Dict[str, Any]) -> None:
    """Upserts the session for the given phone number."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO whatsapp_sessions (phone_number, state, context_data, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (phone_number) DO UPDATE
                    SET state        = EXCLUDED.state,
                        context_data = EXCLUDED.context_data,
                        updated_at   = NOW()
            """, (phone_number, state, json.dumps(context_data)))
        conn.commit()


def delete_whatsapp_session(phone_number: str) -> None:
    """Deletes the session for the given phone number."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM whatsapp_sessions WHERE phone_number = %s",
                (phone_number,)
            )
        conn.commit()
