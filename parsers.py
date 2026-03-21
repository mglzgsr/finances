"""
parsers.py — CSV parsers para Lloyds y HSBC
Extraído de bank_to_notion.py, sin dependencias de Notion.
"""

import csv
import hashlib
from datetime import datetime

# ─── REGLAS DE CATEGORIZACIÓN ───────────────────────────────────────────────
CATEGORY_RULES = {
    "Sueldo / Ingresos":   ["PAYESCAPE", "SALARY", "WAGES", "PAYROLL"],
    "Alquiler cobrado":    ["MONTHLY RENT", "CARLIE COOK", "M IZAGASAURI", "PUCHALT GISEP"],
    "Hipoteca":            ["MTG 40058805579562", "PROSPECT HOLDINGS"],
    "Transferencias":      ["HSBC COMUN", "MIRIAM", "PUCHALT", "DANIEL FERNANDEZ",
                            "RODRIGUEZ DIAZ", "ALBARR", "MARCO GNECCHI",
                            "BEGONA FUENTES", "ALEJANDRA MOENS", "SUNNY ASSI",
                            "MIGUEL SAURI", "M IZAGASAURI", "M Izagasauri",
                            "RAQUEL RODRIGUEZ"],
    "Tarjeta crédito":     ["AMERICAN EXPRESS"],
    "Telefonía":           ["VODAFONE", "O2"],
    "Domiciliaciones":     ["GOCARDLESS"],
    "Inversiones":         ["VANGUARD"],
    "Efectivo / ATM":      ["NOTEMACHINE", "HIGH STREE", "LNK "],
    "Supermercado":        ["EALING BROADWAY", "SIMPLY LOCAL", "TESCO",
                            "SAINSBURY", "WAITROSE", "LIDL", "ALDI", "CO-OP",
                            "M&S FOOD", "MARKS&SPENCER", "SAVERS"],
    "Gasolina":            ["SHELL", "MFG FORLEASE", "BP ", "ESSO", "TEXACO"],
    "Restaurante / Café":  ["JUNIOR'S CAFE", "PRESTO ITALIAN", "SQ *",
                            "CAFE", "RESTAURANT", "PIZZA", "BURGER",
                            "VANILLA CAKES", "EGGFREE CAKE", "FILLING GO"],
    "Salud / Farmacia":    ["PHARMACY", "CHEMIST", "NHS", "DOCTOR", "DENTIST",
                            "KEYCIRCLE", "VITALITY LIFE", "HEALTHY PET"],
    "Colegio / Educación": ["IROCK SCHOOL", "WESTBOROUGH", "SCOPAY",
                            "PAULINE PROVENZANO", "NOAFRI", "DARTNELL"],
    "Ocio / Deporte":      ["PADEL", "GYM", "HOBBLEDOWN", "FIELDS EALING",
                            "CINEMA", "THEATRE", "NATIONAL LOTTERY",
                            "WEST LONDON AERO", "RBWM LIBRARIES", "THE WORKS"],
    "Suministros hogar":   ["OCTOPUS ENERGY", "SOUTH EAST WATER", "WATER",
                            "GAS", "ELECTRIC", "BROADBAND", "INTERNET"],
    "Transporte":          ["TFL TRAVEL", "TRAIN", "BUS", "UBER", "RAIL"],
    "Vivienda / Alquiler": ["CITYGATE", "BLUE CRYSTAL"],
    "Impuestos locales":   ["RBWM COUNCIL TAX", "COUNCIL TAX"],
    "Comisiones banco":    ["CLUB LLOYDS FEE", "LLOYDS FEE", "CLUB LLOYDS WAIVED"],
    "Cashback":            ["LLOYDS CASHBACK", "CASHBACK"],
    "Intereses":           ["INTEREST"],
    "Impuestos / HMRC":    ["HMRC"],
}

def categorize(description: str) -> str:
    desc_upper = description.upper()
    for category, keywords in CATEGORY_RULES.items():
        for kw in keywords:
            if kw.upper() in desc_upper:
                return category
    return "Otros"

def make_hash(date: str, description: str, amount: str, balance: str) -> str:
    raw = f"{date}|{description}|{amount}|{balance}"
    return hashlib.md5(raw.encode()).hexdigest()

# ─── DETECT ──────────────────────────────────────────────────────────────────
def detect_bank(filepath: str) -> str:
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        first_line = f.readline().lower()
    if "transaction type" in first_line and "sort code" in first_line:
        return "lloyds"
    return "hsbc"

# ─── LLOYDS ──────────────────────────────────────────────────────────────────
def parse_lloyds(filepath: str) -> list:
    transactions = []
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            date_str = row["Transaction Date"].strip()
            tx_type  = row["Transaction Type"].strip()
            desc     = row["Transaction Description"].strip()
            debit    = row["Debit Amount"].strip()
            credit   = row["Credit Amount"].strip()
            balance  = row["Balance"].strip()

            is_debit = bool(debit)
            amount   = float(debit if debit else credit)
            date_obj = datetime.strptime(date_str, "%d/%m/%Y")

            transactions.append({
                "date":        date_obj.strftime("%Y-%m-%d"),
                "description": desc,
                "tx_type":     tx_type or "N/A",
                "is_debit":    is_debit,
                "amount":      round(amount, 2),
                "balance":     round(float(balance), 2) if balance else None,
                "category":    categorize(desc),
                "bank":        "Lloyds",
                "hash":        make_hash(date_str, desc, debit or credit, balance),
            })
    return transactions

# ─── HSBC ────────────────────────────────────────────────────────────────────
def parse_hsbc(filepath: str) -> list:
    transactions = []
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 3:
                continue

            date_str = row[0].strip()
            desc     = row[1].strip()
            amount_s = row[2].strip().replace(",", "")

            if not date_str or not amount_s:
                continue

            try:
                amount   = float(amount_s)
                date_obj = datetime.strptime(date_str, "%d/%m/%Y")
            except ValueError:
                continue

            is_debit = amount < 0

            clean_desc = desc
            for suffix in [" )))", " VIS", " DD", " BP", " CR", " IM"]:
                if clean_desc.endswith(suffix):
                    clean_desc = clean_desc[: -len(suffix)].strip()

            tx_type = "N/A"
            if desc.endswith(")))"):   tx_type = "Contactless"
            elif desc.endswith("VIS"): tx_type = "Visa"
            elif desc.endswith("DD"):  tx_type = "DD"
            elif desc.endswith("BP"):  tx_type = "BP"
            elif desc.endswith("CR"):  tx_type = "CR"

            transactions.append({
                "date":        date_obj.strftime("%Y-%m-%d"),
                "description": clean_desc,
                "tx_type":     tx_type,
                "is_debit":    is_debit,
                "amount":      abs(round(amount, 2)),
                "balance":     None,
                "category":    categorize(clean_desc),
                "bank":        "HSBC",
                "hash":        make_hash(date_str, desc, amount_s, ""),
            })
    return transactions
