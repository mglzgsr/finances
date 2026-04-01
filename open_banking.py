"""
open_banking.py — Integración TrueLayer Open Banking
OAuth2 + fetch de transacciones para Lloyds y HSBC.
"""

import os
import hashlib
from urllib.parse import urlencode
from datetime import datetime, timedelta

import httpx
from parsers import categorize

SANDBOX = os.getenv("TRUELAYER_SANDBOX", "true").lower() == "true"

AUTH_URL     = "https://auth.truelayer-sandbox.com" if SANDBOX else "https://auth.truelayer.com"
API_URL      = "https://api.truelayer-sandbox.com"  if SANDBOX else "https://api.truelayer.com"
CLIENT_ID    = os.getenv("TRUELAYER_CLIENT_ID")
CLIENT_SECRET = os.getenv("TRUELAYER_CLIENT_SECRET")
REDIRECT_URI = os.getenv("TRUELAYER_REDIRECT_URI", "https://finances.mglzgsr.com/callback")

SCOPES = "accounts transactions balance offline_access"


def get_auth_url(state: str) -> str:
    """Genera la URL de autorización OAuth para redirigir al usuario."""
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "scope": SCOPES,
        "redirect_uri": REDIRECT_URI,
        "state": state,
        "providers": "uk-ob-all uk-oauth-all",
    }
    return f"{AUTH_URL}/?{urlencode(params)}"


def exchange_code(code: str) -> dict:
    """Intercambia el code de autorización por access + refresh tokens."""
    resp = httpx.post(f"{AUTH_URL}/connect/token", data={
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "redirect_uri": REDIRECT_URI,
    })
    resp.raise_for_status()
    return resp.json()


def refresh_access_token(refresh_token: str) -> dict:
    """Renueva el access token usando el refresh token."""
    resp = httpx.post(f"{AUTH_URL}/connect/token", data={
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
    })
    resp.raise_for_status()
    return resp.json()


def fetch_accounts(access_token: str) -> list:
    """Devuelve la lista de cuentas del usuario."""
    resp = httpx.get(
        f"{API_URL}/data/v1/accounts",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def fetch_transactions(access_token: str, account_id: str, from_date: str = None) -> list:
    """Devuelve transacciones de una cuenta. from_date en formato ISO 8601."""
    params = {}
    if from_date:
        params["from"] = from_date
    resp = httpx.get(
        f"{API_URL}/data/v1/accounts/{account_id}/transactions",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def to_internal_tx(tx: dict, bank: str) -> dict:
    """Convierte una transacción TrueLayer al formato interno de la app."""
    timestamp   = tx.get("timestamp", "")
    date_str    = timestamp[:10] if timestamp else ""
    desc        = tx.get("description", "").strip()
    amount      = float(tx.get("amount", 0))
    is_debit    = amount < 0
    tx_id       = tx.get("transaction_id", "")

    # Balance running si lo incluye TrueLayer (no siempre disponible)
    running     = tx.get("running_balance")
    balance     = float(running["amount"]) if running and "amount" in running else None

    # Hash basado en el ID único de TrueLayer para evitar duplicados
    hash_val = hashlib.md5(f"tl|{tx_id}|{bank}".encode()).hexdigest()

    return {
        "date":        date_str,
        "description": desc,
        "tx_type":     tx.get("transaction_type", "N/A"),
        "is_debit":    is_debit,
        "amount":      round(abs(amount), 2),
        "balance":     round(balance, 2) if balance is not None else None,
        "category":    categorize(desc),
        "bank":        bank,
        "hash":        hash_val,
    }
