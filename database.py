"""
database.py — SQLite persistence layer
Usa sqlite3 estándar, sin dependencias extra.
"""

import sqlite3
import os
from pathlib import Path
from datetime import datetime, date, timedelta
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
                hash        TEXT NOT NULL UNIQUE,
                timestamp   TEXT
            )
        """)
        # Migration: add timestamp column if it doesn't exist yet
        try:
            conn.execute("ALTER TABLE transactions ADD COLUMN timestamp TEXT")
        except Exception:
            pass
        conn.execute("CREATE INDEX IF NOT EXISTS idx_date     ON transactions(date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON transactions(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bank     ON transactions(bank)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bank_connections (
                bank          TEXT PRIMARY KEY,
                access_token  TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                expires_at    TEXT NOT NULL,
                connected_at  TEXT NOT NULL,
                last_sync     TEXT
            )
        """)

def get_conn():
    return sqlite3.connect(DB_PATH)

# ── Write ─────────────────────────────────────────────────────────────────────
def save_transactions(txs: list) -> tuple[int, int]:
    new = skipped = 0
    with get_conn() as conn:
        for tx in txs:
            # Soft-dedup: skip if same date+description+amount+bank already exists
            existing = conn.execute("""
                SELECT 1 FROM transactions
                WHERE date=? AND description=? AND amount=? AND bank=? AND is_debit=?
                LIMIT 1
            """, (
                tx["date"], tx["description"], tx["amount"],
                tx["bank"], 1 if tx["is_debit"] else 0,
            )).fetchone()
            if existing:
                skipped += 1
                continue
            try:
                conn.execute("""
                    INSERT INTO transactions
                        (date, description, tx_type, is_debit, amount, balance, category, bank, hash, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    tx["date"], tx["description"], tx["tx_type"],
                    1 if tx["is_debit"] else 0,
                    tx["amount"], tx["balance"],
                    tx["category"], tx["bank"], tx["hash"],
                    tx.get("timestamp"),
                ))
                new += 1
            except sqlite3.IntegrityError:
                skipped += 1
    return new, skipped

# ── Read ──────────────────────────────────────────────────────────────────────
def _where_clause(year, month, extra: str = "", bank=None) -> tuple[str, list]:
    conds, params = [], []
    if year:
        conds.append("strftime('%Y', date) = ?")
        params.append(str(year))
    if month:
        conds.append("strftime('%m', date) = ?")
        params.append(f"{month:02d}")
    if bank:
        conds.append("bank = ?")
        params.append(bank)
    if extra:
        conds.append(extra)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    return where, params


def get_summary(year=None, month=None, bank=None) -> dict:
    where, params = _where_clause(year, month, bank=bank)
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


def get_monthly_flow(months: int = 6, bank=None) -> list:
    where = "WHERE bank = ?" if bank else ""
    params = [bank] if bank else []
    with get_conn() as conn:
        rows = conn.execute(f"""
            SELECT
                strftime('%Y-%m', date) AS month,
                SUM(CASE WHEN is_debit=0 THEN amount ELSE 0 END) AS income,
                SUM(CASE WHEN is_debit=1 THEN amount ELSE 0 END) AS expenses
            FROM transactions {where}
            GROUP BY month
            ORDER BY month DESC
            LIMIT ?
        """, params + [months]).fetchall()

    result = []
    for month, income, expenses in reversed(rows):
        result.append({
            "month": month,
            "income": round(income, 2),
            "expenses": round(expenses, 2),
            "net": round(income - expenses, 2),
        })
    return result


def get_categories_breakdown(year=None, month=None, bank=None) -> list:
    where, params = _where_clause(year, month, "is_debit=1", bank=bank)
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


def get_transactions(year=None, month=None, category=None, bank=None, is_debit=None, limit=50, offset=0) -> dict:
    conds, params = [], []
    if year:
        conds.append("strftime('%Y', date) = ?")
        params.append(str(year))
    if month:
        conds.append("strftime('%m', date) = ?")
        params.append(f"{month:02d}")
    if category:
        conds.append("category = ?")
        params.append(category)
    if bank:
        conds.append("bank = ?")
        params.append(bank)
    if is_debit is not None:
        conds.append("is_debit = ?")
        params.append(1 if is_debit else 0)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""

    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM transactions {where}", params).fetchone()[0]
        rows  = conn.execute(f"""
            SELECT id, date, description, tx_type, is_debit, amount, balance, category, bank
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
                "id": r[0], "date": r[1], "description": r[2], "tx_type": r[3],
                "is_debit": bool(r[4]), "amount": r[5], "balance": r[6],
                "category": r[7], "bank": r[8],
            }
            for r in rows
        ],
    }


def get_account_balance(bank: str, year=None, month=None) -> dict:
    if bank == "Lloyds":
        return _get_lloyds_balance(year, month)
    return _get_hsbc_balance(year, month)


def _get_lloyds_balance(year=None, month=None) -> dict:
    """Lee el balance real directamente del campo balance del CSV de Lloyds."""
    with get_conn() as conn:
        if year and month:
            end_row = conn.execute("""
                SELECT balance FROM transactions
                WHERE bank='Lloyds' AND strftime('%Y',date)=? AND strftime('%m',date)=?
                AND balance IS NOT NULL
                ORDER BY date DESC, timestamp DESC NULLS LAST, id DESC LIMIT 1
            """, (str(year), f"{month:02d}")).fetchone()

            start_row = conn.execute("""
                SELECT balance FROM transactions
                WHERE bank='Lloyds' AND date < ? AND balance IS NOT NULL
                ORDER BY date DESC, timestamp DESC NULLS LAST, id DESC LIMIT 1
            """, (f"{year}-{month:02d}-01",)).fetchone()
        else:
            end_row = conn.execute("""
                SELECT balance FROM transactions
                WHERE bank='Lloyds' AND balance IS NOT NULL
                ORDER BY date DESC, timestamp DESC NULLS LAST, id DESC LIMIT 1
            """).fetchone()
            start_row = None

    return {
        "current": end_row[0] if end_row else None,
        "previous": start_row[0] if start_row else None,
    }


def _get_hsbc_balance(year=None, month=None) -> dict:
    """Balance HSBC: usa running_balance de TrueLayer si está disponible, si no calcula desde saldo inicial."""
    with get_conn() as conn:
        if year and month:
            # Intenta leer running_balance de TrueLayer para el mes
            end_row = conn.execute("""
                SELECT balance FROM transactions
                WHERE bank='HSBC' AND strftime('%Y',date)=? AND strftime('%m',date)=?
                AND balance IS NOT NULL
                ORDER BY date DESC, timestamp DESC NULLS LAST, id DESC LIMIT 1
            """, (str(year), f"{month:02d}")).fetchone()

            start_row = conn.execute("""
                SELECT balance FROM transactions
                WHERE bank='HSBC' AND date < ? AND balance IS NOT NULL
                ORDER BY date DESC, timestamp DESC NULLS LAST, id DESC LIMIT 1
            """, (f"{year}-{month:02d}-01",)).fetchone()

            if end_row:
                return {
                    "current":  end_row[0],
                    "previous": start_row[0] if start_row else None,
                }
        else:
            end_row = conn.execute("""
                SELECT balance FROM transactions
                WHERE bank='HSBC' AND balance IS NOT NULL
                ORDER BY date DESC, timestamp DESC NULLS LAST, id DESC LIMIT 1
            """).fetchone()

            if end_row:
                return {"current": end_row[0], "previous": None}

    # Fallback: calcula desde saldo inicial + movimientos acumulados
    initial_str = get_setting("initial_balance_hsbc")
    if initial_str is None:
        return {"current": None, "previous": None}

    initial = float(initial_str)

    with get_conn() as conn:
        if year and month:
            period_start = f"{year}-{month:02d}-01"

            net_before = conn.execute("""
                SELECT COALESCE(SUM(CASE WHEN is_debit=0 THEN amount ELSE -amount END), 0)
                FROM transactions WHERE bank='HSBC' AND date < ?
            """, (period_start,)).fetchone()[0]

            net_month = conn.execute("""
                SELECT COALESCE(SUM(CASE WHEN is_debit=0 THEN amount ELSE -amount END), 0)
                FROM transactions WHERE bank='HSBC'
                AND strftime('%Y',date)=? AND strftime('%m',date)=?
            """, (str(year), f"{month:02d}")).fetchone()[0]

            return {
                "current":  round(initial + net_before + net_month, 2),
                "previous": round(initial + net_before, 2),
            }
        else:
            net_total = conn.execute("""
                SELECT COALESCE(SUM(CASE WHEN is_debit=0 THEN amount ELSE -amount END), 0)
                FROM transactions WHERE bank='HSBC'
            """).fetchone()[0]

            return {
                "current":  round(initial + net_total, 2),
                "previous": None,
            }


def update_transaction_category(tx_id: int, category: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE transactions SET category = ? WHERE id = ?",
            (category, tx_id)
        )
        return cur.rowcount > 0


def get_all_categories() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT category FROM transactions ORDER BY category"
        ).fetchall()
    return [r[0] for r in rows]


# ── Bank connections ──────────────────────────────────────────────────────────
def save_connection(bank: str, access_token: str, refresh_token: str, expires_in: int):
    expires_at   = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()
    connected_at = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO bank_connections (bank, access_token, refresh_token, expires_at, connected_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(bank) DO UPDATE SET
                access_token=excluded.access_token,
                refresh_token=excluded.refresh_token,
                expires_at=excluded.expires_at,
                connected_at=excluded.connected_at
        """, (bank, access_token, refresh_token, expires_at, connected_at))


def get_connection(bank: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("""
            SELECT bank, access_token, refresh_token, expires_at, connected_at, last_sync
            FROM bank_connections WHERE bank = ?
        """, (bank,)).fetchone()
    if not row:
        return None
    return {
        "bank": row[0], "access_token": row[1], "refresh_token": row[2],
        "expires_at": row[3], "connected_at": row[4], "last_sync": row[5],
    }


def get_all_connections() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT bank, connected_at, last_sync FROM bank_connections"
        ).fetchall()
    return [{"bank": r[0], "connected_at": r[1], "last_sync": r[2]} for r in rows]


def update_sync_time(bank: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE bank_connections SET last_sync = ? WHERE bank = ?",
            (datetime.utcnow().isoformat(), bank)
        )


def get_setting(key: str, default=None):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value)
        )
