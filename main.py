"""
main.py — Finance Dashboard API
FastAPI backend: recibe CSVs, parsea, guarda en SQLite y sirve datos al dashboard.
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import tempfile, os, shutil
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR / "frontend"

from database import (
    init_db, save_transactions, get_summary, get_transactions,
    get_monthly_flow, get_categories_breakdown, update_transaction_category,
    get_all_categories, get_setting, set_setting, get_account_balance,
)
from parsers import detect_bank, parse_lloyds, parse_hsbc, CATEGORY_RULES

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
    limit: int = 50,
    offset: int = 0,
):
    return get_transactions(year=year, month=month, category=category, bank=bank, limit=limit, offset=offset)

@app.get("/api/balance")
def balance(
    bank: str,
    year: Optional[int] = None,
    month: Optional[int] = None,
):
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
