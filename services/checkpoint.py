import json
import sqlite3
from typing import Dict, Any, Optional
from services.database import get_db_connection

def init_checkpoint_table():
    """Ensures checkpoint storage table exists in SQLite database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_checkpoints (
            job_id TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.commit()

def save_checkpoint(job_id: str, state_data: Dict[str, Any]):
    """Saves or updates job execution checkpoint state."""
    init_checkpoint_table()
    serialized = json.dumps(state_data, ensure_ascii=False)
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO job_checkpoints (job_id, state, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (job_id, serialized))
        conn.commit()

def get_checkpoint(job_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves persisted checkpoint state for a job, if available."""
    init_checkpoint_table()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT state FROM job_checkpoints WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        if row and row["state"]:
            try:
                return json.loads(row["state"])
            except Exception:
                return None
    return None

def clear_checkpoint(job_id: str):
    """Removes checkpoint state once job finishes cleanly."""
    init_checkpoint_table()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM job_checkpoints WHERE job_id = ?", (job_id,))
        conn.commit()

# Ensure table exists on import
init_checkpoint_table()
