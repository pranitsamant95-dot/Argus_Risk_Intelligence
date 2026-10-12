"""Load and validate canonical financial rows. Missing values stay None (never zero)."""
import csv, hashlib, io
from pathlib import Path

NUMERIC = ["revenue", "operating_profit", "total_assets", "cash_and_equivalents", "current_assets",
           "current_liabilities", "total_debt", "short_term_debt", "long_term_debt", "operating_cash_flow",
           "capital_expenditure", "interest_expense", "receivables", "inventory", "payables"]
CRITICAL = ["revenue", "operating_profit", "cash_and_equivalents", "current_assets", "current_liabilities",
            "total_debt", "interest_expense", "operating_cash_flow"]
DEMO_PATH = Path(__file__).resolve().parents[2] / "data" / "demo" / "company_financials.csv"


def parse_csv_text(text: str):
    lines = [l for l in text.splitlines() if not l.startswith("#")]
    rows = []
    for r in csv.DictReader(io.StringIO("\n".join(lines))):
        for k in NUMERIC:
            v = (r.get(k) or "").strip()
            try:
                r[k] = float(v) if v != "" else None
            except ValueError:
                r[k] = None
        rows.append(r)
    return rows


def load_demo():
    text = DEMO_PATH.read_text(encoding="utf-8")
    return parse_csv_text(text), hashlib.sha256(text.encode()).hexdigest()[:16]


def validate(rows):
    """Return list of {severity, message}: critical gaps, duplicates, mixed units, jumps, balance sanity."""
    issues, seen = [], set()
    if not rows:
        return [{"severity": "error", "message": "No rows loaded."}]
    for r in rows:
        p = r.get("reporting_period")
        if p in seen:
            issues.append({"severity": "error", "message": f"Duplicate reporting period {p}."})
        seen.add(p)
        miss = [k for k in CRITICAL if r.get(k) is None]
        if miss:
            issues.append({"severity": "warning", "message": f"{p}: missing {', '.join(miss)} (not imputed)."})
        if r.get("current_assets") and r.get("cash_and_equivalents") and r["cash_and_equivalents"] > r["current_assets"]:
            issues.append({"severity": "error", "message": f"{p}: cash exceeds current assets."})
        if r.get("short_term_debt") and r.get("total_debt") and r["short_term_debt"] > r["total_debt"]:
            issues.append({"severity": "error", "message": f"{p}: short-term debt exceeds total debt."})
    if len({r.get("currency") for r in rows}) > 1 or len({r.get("units") for r in rows}) > 1:
        issues.append({"severity": "error", "message": "Mixed currency or units; normalise before analysis."})
    if len({r.get("period_type") for r in rows}) > 1:
        issues.append({"severity": "error", "message": "Annual and quarterly rows mixed; analyse separately to avoid double counting."})
    for a, b in zip(rows, rows[1:]):
        if a.get("revenue") and b.get("revenue") and abs(b["revenue"] / a["revenue"] - 1) > 0.4:
            issues.append({"severity": "warning", "message": f"{b['reporting_period']}: revenue moved >40% vs prior period."})
    return issues


def quality_status(issues):
    if any(i["severity"] == "error" for i in issues):
        return "Errors found"
    return "Warnings" if issues else "Passed internal checks"  # internal status, not an industry rating
