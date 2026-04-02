"""
main.py — Finance Dashboard API
FastAPI backend: recibe CSVs, parsea, guarda en SQLite y sirve datos al dashboard.
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
import tempfile, os, shutil
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR / "frontend"

from database import (
    init_db, save_transactions, get_summary, get_transactions,
    get_monthly_flow, get_categories_breakdown, update_transaction_category,
    get_all_categories, get_setting, set_setting, get_account_balance,
    save_connection, get_connection, get_all_connections, update_sync_time,
    update_current_balance, get_all_accounts, get_account, create_account,
    update_account_balance,
)
from parsers import detect_bank, parse_lloyds, parse_hsbc, CATEGORY_RULES
import open_banking as ob

app = FastAPI(title="Finance Dashboard", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://192\.168\.0\.\d{1,3}(:\d+)?|http://localhost(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    init_db()

# ── Static frontend ──────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

@app.get("/")
def root():
    return FileResponse(FRONTEND_DIR / "index.html")

# ── Upload CSV ───────────────────────────────────────────────────────────────
@app.post("/api/upload")
async def upload_csv(files: list[UploadFile] = File(...)):
    results = []

    for file in files:
        suffix = os.path.splitext(file.filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name

        try:
            bank = detect_bank(tmp_path)
            if bank == "lloyds":
                txs = parse_lloyds(tmp_path)
            else:
                txs = parse_hsbc(tmp_path)

            new, skipped = save_transactions(txs)
            results.append({
                "filename": file.filename,
                "bank": bank.capitalize(),
                "parsed": len(txs),
                "new": new,
                "skipped": skipped,
            })
        except Exception as e:
            results.append({"filename": file.filename, "error": str(e)})
        finally:
            os.unlink(tmp_path)

    return {"results": results}

# ── Data endpoints ───────────────────────────────────────────────────────────
@app.get("/api/summary")
def summary(
    year: Optional[int] = None,
    month: Optional[int] = None,
    bank: Optional[str] = None,
):
    return get_summary(year=year, month=month, bank=bank)

@app.get("/api/monthly-flow")
def monthly_flow(months: int = 6, bank: Optional[str] = None):
    return get_monthly_flow(months=months, bank=bank)

@app.get("/api/categories")
def categories(
    year: Optional[int] = None,
    month: Optional[int] = None,
    bank: Optional[str] = None,
):
    return get_categories_breakdown(year=year, month=month, bank=bank)

@app.get("/api/transactions")
def transactions(
    year: Optional[int] = None,
    month: Optional[int] = None,
    category: Optional[str] = None,
    bank: Optional[str] = None,
    is_debit: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
):
    return get_transactions(year=year, month=month, category=category, bank=bank, is_debit=is_debit, limit=limit, offset=offset)

@app.get("/api/balance")
def balance(
    bank: str,
    year: Optional[int] = None,
    month: Optional[int] = None,
):
    # Para saldo actual, usar el balance guardado en accounts si está disponible
    if not year and not month:
        acc = get_account(bank)
        if acc and acc.get("current_balance") is not None:
            return {"current": acc["current_balance"], "previous": None}
    return get_account_balance(bank=bank, year=year, month=month)


class CategoryUpdate(BaseModel):
    category: str

@app.patch("/api/transactions/{tx_id}/category")
def patch_category(tx_id: int, body: CategoryUpdate):
    ok = update_transaction_category(tx_id, body.category)
    if not ok:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"ok": True}

@app.get("/api/category-list")
def category_list():
    db_cats = get_all_categories()
    all_cats = sorted(set(list(CATEGORY_RULES.keys()) + db_cats + ["Otros"]))
    return all_cats


# ── Accounts ─────────────────────────────────────────────────────────────────
class AccountCreate(BaseModel):
    slug: str
    display_name: str
    account_type: str = "current"
    currency: str = "GBP"
    source: str = "manual"
    connection_id: Optional[str] = None
    sort_order: int = 0

@app.get("/api/accounts")
def accounts_list():
    return get_all_accounts()

@app.post("/api/accounts")
def accounts_create(body: AccountCreate):
    create_account(
        slug=body.slug,
        display_name=body.display_name,
        account_type=body.account_type,
        currency=body.currency,
        source=body.source,
        connection_id=body.connection_id,
        sort_order=body.sort_order,
    )
    return get_account(body.slug)


# ── Open Banking ─────────────────────────────────────────────────────────────
@app.get("/connect")
def connect(bank: str):
    """Inicia el flujo OAuth de TrueLayer para el banco indicado."""
    return RedirectResponse(ob.get_auth_url(state=bank))


@app.get("/callback")
def callback(code: str, state: str):
    """TrueLayer redirige aquí tras autenticación. Guarda tokens y auto-descubre cuentas."""
    try:
        tokens = ob.exchange_code(code)
        access_token = tokens["access_token"]
        save_connection(
            bank=state,
            access_token=access_token,
            refresh_token=tokens["refresh_token"],
            expires_in=tokens.get("expires_in", 3600),
        )
        # Auto-discover accounts and cards from TrueLayer
        tl_accounts = ob.fetch_accounts(access_token)
        tl_cards    = ob.fetch_cards(access_token)
        for i, tl_acc in enumerate(tl_accounts):
            acc = ob.account_to_internal(tl_acc, connection_id=state, sort_order=i)
            create_account(**acc)
        for i, tl_card in enumerate(tl_cards):
            acc = ob.card_to_internal(tl_card, connection_id=state, sort_order=len(tl_accounts) + i)
            create_account(**acc)
    except Exception as e:
        return RedirectResponse(f"/?error={str(e)}")
    return RedirectResponse("/?connected=true")


@app.post("/api/sync")
def sync(bank: str):
    """Sincroniza transacciones de TrueLayer para el banco indicado."""
    conn_data = get_connection(bank)
    if not conn_data:
        raise HTTPException(status_code=404, detail="Banco no conectado")

    # Refrescar token si caduca en menos de 5 minutos
    expires_at = datetime.fromisoformat(conn_data["expires_at"])
    if (expires_at - datetime.utcnow()).total_seconds() < 300:
        tokens = ob.refresh_access_token(conn_data["refresh_token"])
        save_connection(bank, tokens["access_token"], tokens["refresh_token"], tokens.get("expires_in", 3600))
        access_token = tokens["access_token"]
    else:
        access_token = conn_data["access_token"]

    from_date = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%dT00:00:00Z")
    tl_accounts = ob.fetch_accounts(access_token)
    tl_cards    = ob.fetch_cards(access_token)
    total_new = total_skipped = 0

    # Ensure accounts and cards are registered
    for i, tl_acc in enumerate(tl_accounts):
        create_account(**ob.account_to_internal(tl_acc, connection_id=bank, sort_order=i))
    for i, tl_card in enumerate(tl_cards):
        create_account(**ob.card_to_internal(tl_card, connection_id=bank, sort_order=len(tl_accounts) + i))

    # Sync accounts
    for tl_acc in tl_accounts:
        slug = ob.account_to_internal(tl_acc, connection_id=bank)["slug"]
        txs_raw = ob.fetch_transactions(access_token, tl_acc["account_id"], from_date)
        txs = [ob.to_internal_tx(t, slug) for t in txs_raw]
        new, skipped = save_transactions(txs)
        total_new += new
        total_skipped += skipped
        bal = ob.fetch_balance(access_token, tl_acc["account_id"])
        if bal is not None:
            update_account_balance(slug, round(bal, 2))

    # Sync cards
    for tl_card in tl_cards:
        slug = ob.card_to_internal(tl_card, connection_id=bank)["slug"]
        txs_raw = ob.fetch_card_transactions(access_token, tl_card["account_id"], from_date)
        txs = [ob.to_internal_tx(t, slug) for t in txs_raw]
        new, skipped = save_transactions(txs)
        total_new += new
        total_skipped += skipped
        bal = ob.fetch_card_balance(access_token, tl_card["account_id"])
        if bal is not None:
            update_account_balance(slug, round(bal, 2))

    update_sync_time(bank)
    return {"bank": bank, "new": total_new, "skipped": total_skipped}


@app.get("/api/connections")
def connections():
    """Estado de las conexiones Open Banking por banco."""
    return {c["bank"]: c for c in get_all_connections()}


class SettingsUpdate(BaseModel):
    initial_balance_hsbc: Optional[float] = None

@app.get("/api/settings")
def get_settings():
    val = get_setting("initial_balance_hsbc")
    return {"initial_balance_hsbc": float(val) if val is not None else None}

@app.patch("/api/settings")
def patch_settings(body: SettingsUpdate):
    if body.initial_balance_hsbc is not None:
        set_setting("initial_balance_hsbc", str(body.initial_balance_hsbc))
    return {"ok": True}
