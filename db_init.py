#!/usr/bin/env python3
"""Initialize database schema properly."""
import sqlite3
from pathlib import Path

def init_database(db_path):
    """Initialize all required database tables."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Create routing_metrics table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS routing_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type TEXT NOT NULL,
            provider TEXT NOT NULL,
            success BOOLEAN NOT NULL,
            response_time REAL NOT NULL,
            tokens_used INTEGER DEFAULT 0,
            created_at REAL NOT NULL,
            UNIQUE(task_type, provider, created_at)
        )
    ''')

    # Create provider health table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS provider_health (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT UNIQUE NOT NULL,
            state TEXT DEFAULT 'unknown',
            last_check REAL,
            retry_at REAL
        )
    ''')

    # Create context table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS llm_context (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace TEXT NOT NULL,
            llm TEXT NOT NULL,
            context TEXT,
            created_at REAL,
            UNIQUE(workspace, llm)
        )
    ''')

    # Create runs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            state TEXT,
            title TEXT,
            created_at REAL,
            completed_at REAL
        )
    ''')

    conn.commit()
    conn.close()
    print(f"✓ Database initialized: {db_path}")

if __name__ == '__main__':
    db_path = Path.home() / '.war-room-state' / 'state.sqlite3'
    init_database(str(db_path))
