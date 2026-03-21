"""
main.py — Finance Dashboard API
FastAPI backend: recibe CSVs, parsea, guarda en SQLite y sirve datos al dashboard.
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import tempfile, os, shutil
from typing import Optional

from database import init_db, save_transactions, get_summary, get_transactions, get_monthly_flow, get_categories_breakdown
from parsers import detect_bank, parse_lloyds, parse_hsbc

app = FastAPI(title="Finance Dashboard", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    init_db()

# ── Static frontend ──────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="../frontend"), name="static")

@app.get("/")
def root():
    return FileResponse("../frontend/index.html")

# ── Upload CSV ───────────────────────────────────────────────────────────────
@app.post("/api/upload")
async def upload_csv(files: list[UploadFile] = File(...)):
    results = []

    for file in files:
        # Guardar temporalmente
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
def summary(year: Optional[int] = None, month: Optional[int] = None):
    return get_summary(year=year, month=month)

@app.get("/api/monthly-flow")
def monthly_flow(months: int = 6):
    return get_monthly_flow(months=months)

@app.get("/api/categories")
def categories(year: Optional[int] = None, month: Optional[int] = None):
    return get_categories_breakdown(year=year, month=month)

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
