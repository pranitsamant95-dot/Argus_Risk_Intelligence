"""One-quarter-ahead operating/cash scenario model. Every relationship is explicit.

All INR crore, quarterly, relative to the latest observed quarter:
  revenue_s  = revenue * (1 + revenue_change)
  op_profit  = revenue_s * (base_margin - margin_compression); opex_cut then applied to the implied cost base
  interest_s = interest + total_debt * floating_share * rate_shock/10000 / 4  (only the ASSUMED floating share reprices)
  receivables_s = receivables + base_revenue/90 * collection_delay_days  (no working-capital release is credited from
                  lower sales inside the quarter: conservative, since collections lag sales)
  inventory_s = inventory * (1 + inventory_build)
  OCF_s = OCF + d(op_profit) - d(interest) - d(receivables) - d(inventory)  (tax, payables, other items held constant)
  refinancing_outflow = short_term_debt * refinancing_shortfall
  closing_cash = cash + OCF_s - capex - refinancing_outflow
  liquidity_buffer_required = 30 days of stressed operating costs; funding_gap = max(0, buffer - closing_cash)
"""
from dataclasses import dataclass, asdict, replace
from src.finance import metrics as m


@dataclass(frozen=True)
class Assumptions:
    revenue_change: float = 0.0
    margin_compression: float = 0.0
    rate_shock_bps: float = 0.0
    floating_share: float = 0.40          # ASSUMPTION: debt composition is not in the data
    collection_delay_days: float = 0.0
    inventory_build: float = 0.0
    refinancing_shortfall: float = 0.0
    opex_cut: float = 0.0
    covenant_min_icr: float = 2.0         # ILLUSTRATIVE assumption, not a real covenant

    def validate(self):
        errs = []
        for k, lo, hi in [("revenue_change", -0.9, 1.0), ("margin_compression", -0.1, 0.5), ("rate_shock_bps", -500, 1500),
                          ("floating_share", 0, 1), ("collection_delay_days", -30, 180), ("inventory_build", -0.5, 2.0),
                          ("refinancing_shortfall", 0, 1), ("opex_cut", 0, 0.5)]:
            if not lo <= getattr(self, k) <= hi:
                errs.append(f"{k} must be within [{lo}, {hi}]")
        return errs


PRESETS = {
    "Base case": Assumptions(),
    "Adverse case": Assumptions(revenue_change=-0.08, margin_compression=0.02, rate_shock_bps=150,
                                collection_delay_days=10, inventory_build=0.08, refinancing_shortfall=0.15),
    "Severe stress": Assumptions(revenue_change=-0.20, margin_compression=0.05, rate_shock_bps=300,
                                 collection_delay_days=25, inventory_build=0.20, refinancing_shortfall=0.40),
}
NEEDED = ["revenue", "operating_profit", "interest_expense", "total_debt", "short_term_debt", "receivables",
          "inventory", "operating_cash_flow", "capital_expenditure", "cash_and_equivalents"]


def run_scenario(base: dict, a: Assumptions) -> dict:
    errs = a.validate()
    if errs:
        raise ValueError("; ".join(errs))
    missing = [k for k in NEEDED if base.get(k) is None]
    if missing:
        raise ValueError(f"Scenario cannot run; missing inputs: {missing}")
    if base["revenue"] <= 0:
        raise ValueError("Scenario cannot run; base revenue must be positive")
    rev = base["revenue"] * (1 + a.revenue_change)
    margin = base["operating_profit"] / base["revenue"]
    op = rev * (margin - a.margin_compression)
    op += a.opex_cut * (rev - op)
    interest = base["interest_expense"] + base["total_debt"] * a.floating_share * a.rate_shock_bps / 10000 / 4
    d_recv = base["revenue"] / m.DAYS_PER_QUARTER * a.collection_delay_days
    d_inv = base["inventory"] * a.inventory_build
    ocf = (base["operating_cash_flow"] + (op - base["operating_profit"]) - (interest - base["interest_expense"])
           - d_recv - d_inv)
    refi = base["short_term_debt"] * a.refinancing_shortfall
    closing = base["cash_and_equivalents"] + ocf - base["capital_expenditure"] - refi
    buffer = max(rev - op, 0) / 3
    icr = m.sdiv(op, interest)
    return {"assumptions": asdict(a), "revenue": rev, "operating_profit": op,
            "operating_margin": op / rev if rev > 0 else None, "interest_expense": interest, "interest_coverage": icr,
            "operating_cash_flow": ocf, "working_capital_investment": d_recv + d_inv, "refinancing_outflow": refi,
            "closing_cash": closing, "liquidity_buffer_required": buffer, "funding_gap": max(0.0, buffer - closing),
            "covenant_headroom_icr": None if icr is None else (icr - a.covenant_min_icr) / a.covenant_min_icr,
            "debt_service_proxy": interest + refi}


SENSITIVITY_SHOCKS = {"revenue_change": -0.10, "margin_compression": 0.02, "rate_shock_bps": 200,
                      "collection_delay_days": 15, "inventory_build": 0.15, "refinancing_shortfall": 0.25}


def sensitivity(base: dict, a: Assumptions = Assumptions()) -> dict:
    """One-at-a-time effect on closing cash of a fixed incremental shock."""
    ref = run_scenario(base, a)["closing_cash"]
    return {k: {"shock": s, "delta_closing_cash":
                run_scenario(base, replace(a, **{k: getattr(a, k) + s}))["closing_cash"] - ref}
            for k, s in SENSITIVITY_SHOCKS.items()}
