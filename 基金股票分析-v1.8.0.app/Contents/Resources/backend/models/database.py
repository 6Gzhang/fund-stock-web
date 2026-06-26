import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            shares REAL NOT NULL DEFAULT 0,
            avg_cost REAL NOT NULL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            action TEXT NOT NULL,
            shares REAL NOT NULL,
            price REAL NOT NULL,
            amount REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()


# --- 持仓操作 ---
def get_positions():
    conn = get_db()
    rows = conn.execute("SELECT * FROM positions ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_position(code: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM positions WHERE code = ?", (code,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_position(code: str, name: str, ptype: str, shares: float, avg_cost: float):
    conn = get_db()
    existing = conn.execute("SELECT * FROM positions WHERE code = ?", (code,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE positions SET name=?, type=?, shares=?, avg_cost=?, updated_at=? WHERE code=?",
            (name, ptype, shares, avg_cost, datetime.now().isoformat(), code),
        )
    else:
        conn.execute(
            "INSERT INTO positions (code, name, type, shares, avg_cost, updated_at) VALUES (?,?,?,?,?,?)",
            (code, name, ptype, shares, avg_cost, datetime.now().isoformat()),
        )
    conn.commit()
    conn.close()


def delete_position(code: str):
    conn = get_db()
    conn.execute("DELETE FROM positions WHERE code = ?", (code,))
    conn.commit()
    conn.close()


# --- 交易记录 ---
def add_trade(code: str, name: str, ptype: str, action: str, shares: float, price: float, amount: float):
    conn = get_db()
    conn.execute(
        "INSERT INTO trades (code, name, type, action, shares, price, amount, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (code, name, ptype, action, shares, price, amount, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_trades(limit: int = 50):
    conn = get_db()
    rows = conn.execute("SELECT * FROM trades ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- 自选列表 ---
def get_watchlist():
    conn = get_db()
    rows = conn.execute("SELECT * FROM watchlist ORDER BY added_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_to_watchlist(code: str, name: str, ptype: str):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO watchlist (code, name, type, added_at) VALUES (?,?,?,?)",
            (code, name, ptype, datetime.now().isoformat()),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()


def remove_from_watchlist(code: str):
    conn = get_db()
    conn.execute("DELETE FROM watchlist WHERE code = ?", (code,))
    conn.commit()
    conn.close()