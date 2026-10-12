"""Upload parsing and canonicalisation for CSV/XLSX financial statement files."""
from __future__ import annotations
from io import BytesIO
import csv

NUMERIC_FIELDS = ["revenue", "operating_profit", "total_assets", "cash_and_equivalents", "current_assets",
    "current_liabilities", "total_debt", "short_term_debt", "long_term_debt", "operating_cash_flow",
    "capital_expenditure", "interest_expense", "receivables", "inventory", "payables"]


def canonicalise(rows: list[dict], source_name: str = "user upload") -> list[dict]:
    if not rows:
        raise ValueError("The uploaded file contains no data rows.")
    output = []
    for i, original in enumerate(rows):
        r = {str(k).strip(): v for k, v in original.items() if k is not None}
        # Normalise common heading variants without silently guessing numerical values.
        aliases = {field.replace("_", " "): field for field in NUMERIC_FIELDS}
        aliases.update({"period": "reporting_period", "quarter": "reporting_period", "company": "company_name",
                   "company name": "company_name", "cash": "cash_and_equivalents", "operating cash flow": "operating_cash_flow",
                   "short term debt": "short_term_debt", "long term debt": "long_term_debt"})
        for k in list(r):
            norm = k.strip().lower().replace("-", " ").replace("_", " ")
            target = aliases.get(norm)
            if target and target not in r:
                r[target] = r.pop(k)
        for k in NUMERIC_FIELDS:
            v = r.get(k)
            if v is None or (isinstance(v, str) and not v.strip()):
                r[k] = None
            else:
                try:
                    r[k] = float(str(v).replace(",", "").strip())
                except (TypeError, ValueError):
                    r[k] = None
        r["company_id"] = str(r.get("company_id") or "UPLOAD")
        r["company_name"] = str(r.get("company_name") or "Uploaded Company")
        r["sector"] = str(r.get("sector") or "Not specified")
        r["reporting_period"] = str(r.get("reporting_period") or f"Period {i+1}")
        r["period_type"] = str(r.get("period_type") or "quarterly").lower()
        r["currency"] = str(r.get("currency") or "INR")
        r["units"] = str(r.get("units") or "crore")
        r["data_origin"] = "user-supplied"
        r["source_document"] = str(r.get("source_document") or source_name)
        output.append(r)
    return output


def parse_uploaded_file(filename: str, file_bytes: bytes) -> list[dict]:
    lower = filename.lower()
    if lower.endswith(".csv"):
        text = file_bytes.decode("utf-8-sig", errors="replace")
        lines = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
        rows = list(csv.DictReader(lines))
    elif lower.endswith(".xlsx") or lower.endswith(".xls"):
        try:
            import pandas as pd
            frame = pd.read_excel(BytesIO(file_bytes))
            frame = frame.where(frame.notna(), None)
            rows = frame.to_dict(orient="records")
        except ImportError as exc:
            raise RuntimeError("Excel upload requires pandas and openpyxl. Install requirements.txt.") from exc
        except Exception as exc:
            raise ValueError(f"Could not read spreadsheet: {exc}") from exc
    else:
        raise ValueError("Supported financial data formats are CSV and XLSX.")
    return canonicalise(rows, filename)
