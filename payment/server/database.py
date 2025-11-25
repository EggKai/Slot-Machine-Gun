# Code generated with assistance from ChatGPT (OpenAI)
# Date generated: Nov 2025
# Modified for ICT1011 Project

import sqlite3
from pathlib import Path

DB_PATH = Path("shop.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        is_admin INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS rfid_cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rfid_id TEXT UNIQUE,
        credits INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        national_id TEXT UNIQUE NOT NULL,
        address TEXT,
        age INTEGER,
        rfid_id TEXT UNIQUE,
        FOREIGN KEY (rfid_id) REFERENCES rfid_cards(rfid_id)
    )
    """)

    conn.commit()
    conn.close()

def get_connection():
    return sqlite3.connect(DB_PATH)