"""Deterministic financial metrics. Undefined (zero/negative denominator or missing input) -> None."""
DAYS_PER_QUARTER = 90


def sdiv(n, d):
    if n is None or d is None or d <= 0:
        return None
    return n / d


def current_ratio(r): return sdiv(r.get("current_assets"), r.get("current_liabilities"))


def quick_ratio(r):
    if r.get("current_assets") is None or r.get("inventory") is None:
        return None
    return sdiv(r["current_assets"] - r["inventory"], r.get("current_liabilities"))


def interest_coverage(r): return sdiv(r.get("operating_profit"), r.get("interest_expense"))
def operating_margin(r): return sdiv(r.get("operating_profit"), r.get("revenue"))
def debt_to_assets(r): return sdiv(r.get("total_debt"), r.get("total_assets"))
def cash_to_short_term_debt(r): return sdiv(r.get("cash_and_equivalents"), r.get("short_term_debt"))


def free_cash_flow(r):
    if r.get("operating_cash_flow") is None or r.get("capital_expenditure") is None:
        return None
    return r["operating_cash_flow"] - r["capital_expenditure"]


def _days(num, r):
    x = sdiv(num, r.get("revenue"))
    return None if x is None else x * DAYS_PER_QUARTER


def dso(r): return _days(r.get("receivables"), r)
def dio(r): return _days(r.get("inventory"), r)   # revenue-based proxy (COGS not in schema)
def dpo(r): return _days(r.get("payables"), r)    # revenue-based proxy


def cash_conversion_cycle(r):
    parts = [dso(r), dio(r), dpo(r)]
    return None if any(p is None for p in parts) else parts[0] + parts[1] - parts[2]


def growth(rows, key, lag=1):
    if len(rows) <= lag or rows[-1].get(key) is None or rows[-1 - lag].get(key) in (None, 0):
        return None
    return rows[-1][key] / rows[-1 - lag][key] - 1


def snapshot(r):
    return {"current_ratio": current_ratio(r), "quick_ratio": quick_ratio(r), "interest_coverage": interest_coverage(r),
            "operating_margin": operating_margin(r), "debt_to_assets": debt_to_assets(r),
            "cash_to_short_term_debt": cash_to_short_term_debt(r), "free_cash_flow": free_cash_flow(r),
            "dso": dso(r), "dio_revenue_proxy": dio(r), "dpo_revenue_proxy": dpo(r),
            "cash_conversion_cycle_proxy": cash_conversion_cycle(r)}
