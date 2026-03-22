"""
database.py — SQLite persistence layer
Usa sqlite3 estándar, sin dependencias extra.
"""

import sqlite3
import os
from pathlib import Path
from datetime import datetime, date
from typing import Optional
from collections import defaultdict

_DEFAULT_DB = Path(__file__).parent / "data" / "finance.db"
DB_PATH = os.environ.get("DB_PATH", str(_DEFAULT_DB))

# ── Schema ────────────────────────────────────────────────────────────────────
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL,
                description TEXT NOT NULL,
                tx_type     TEXT,
                is_debit    INTEGER NOT NULL,
                amount      REAL NOT NULL,
                balance     REAL,
                category    TEXT NOT NULL,
                bank        TEXT NOT NULL,
                hash        TEXT NOT NULL UNIQUE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_date     ON transactions(date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON transactions(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bank     ON transactions(bank)")

def get_conn():
    return sqlite3.connect(DB_PATH)

# ── Write ─────────────────────────────────────────────────────────────────────
def save_transactions(txs: list) -> tuple[int, int]:
    new = skipped = 0
    with get_conn() as conn:
        for tx in txs:
            try:
                conn.execute("""
                    INSERT INTO transactions
                        (date, description, tx_type, is_debit, amount, balance, category, bank, hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    tx["date"], tx["description"], tx["tx_type"],
                    1 if tx["is_debit"] else 0,
                    tx["amount"], tx["balance"],
                    tx["category"], tx["bank"], tx["hash"],
                ))
                new += 1
            except sqlite3.IntegrityError:
                skipped += 1
    return new, skipped

# ── Read ──────────────────────────────────────────────────────────────────────
def _where_clause(year, month, extra: str = "") -> tuple[str, list]:
    conds, params = [], []
    if year:
        conds.append("strftime('%Y', date) = ?")
        params.append(str(year))
    if month:
        conds.append("strftime('%m', date) = ?")
        params.append(f"{month:02d}")
    if extra:
        conds.append(extra)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    return where, params


def get_summary(year=None, month=None) -> dict:
    where, params = _where_clause(year, month)
    with get_conn() as conn:
        row = conn.execute(f"""
            SELECT
                COALESCE(SUM(CASE WHEN is_debit=0 THEN amount ELSE 0 END), 0) AS income,
                COALESCE(SUM(CASE WHEN is_debit=1 THEN amount ELSE 0 END), 0) AS expenses,
                COUNT(*) AS tx_count,
                MIN(date) AS from_date,
                MAX(date) AS to_date
            FROM transactions {where}
        """, params).fetchone()

    income, expenses, tx_count, from_date, to_date = row
    net = income - expenses
    savings_rate = round((net / income * 100), 1) if income > 0 else 0

    return {
        "income": round(income, 2),
        "expenses": round(expenses, 2),
        "net": round(net, 2),
        "savings_rate": savings_rate,
        "tx_count": tx_count,
        "from_date": from_date,
        "to_date": to_date,
    }


def get_monthly_flow(months: int = 6) -> list:
    with get_conn() as conn:
        rows = conn.execute(f"""
            SELECT
                strftime('%Y-%m', date) AS month,
                SUM(CASE WHEN is_debit=0 THEN amount ELSE 0 END) AS income,
                SUM(CASE WHEN is_debit=1 THEN amount ELSE 0 END) AS expenses
            FROM transactions
            GROUP BY month
            ORDER BY month DESC
            LIMIT ?
        """, (months,)).fetchall()

    result = []
    for month, income, expenses in reversed(rows):
        result.append({
            "month": month,
            "income": round(income, 2),
            "expenses": round(expenses, 2),
            "net": round(income - expenses, 2),
        })
    return result


def get_categories_breakdown(year=None, month=None) -> list:
    where, params = _where_clause(year, month, "is_debit=1")
    with get_conn() as conn:
        rows = conn.execute(f"""
            SELECT category, SUM(amount) AS total, COUNT(*) AS count
            FROM transactions
            {where}
            GROUP BY category
            ORDER BY total DESC
        """, params).fetchall()

    total_expenses = sum(r[1] for r in rows)
    return [
        {
            "category": r[0],
            "amount": round(r[1], 2),
            "count": r[2],
            "pct": round(r[1] / total_expenses * 100, 1) if total_expenses > 0 else 0,
        }
        for r in rows
    ]


def get_transactions(year=None, month=None, category=None, bank=None, limit=50, offset=0) -> dict:
    extra_conds = []
    if category:
        extra_conds.append(f"category = '{category}'")
    if bank:
        extra_conds.append(f"bank = '{bank}'")

    where, params = _where_clause(year, month, " AND ".join(extra_conds))

    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM transactions {where}", params).fetchone()[0]
        rows  = conn.execute(f"""
            SELECT date, description, tx_type, is_debit, amount, balance, category, bank
            FROM transactions {where}
            ORDER BY date DESC, id DESC
            LIMIT ? OFFSET ?
        """, params + [limit, offset]).fetchall()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "transactions": [
            {
                "date": r[0], "description": r[1], "tx_type": r[2],
                "is_debit": bool(r[3]), "amount": r[4], "balance": r[5],
                "category": r[6], "bank": r[7],
            }
            for r in rows
        ],
    }
