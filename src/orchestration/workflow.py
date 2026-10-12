"""Explicit sequential state machine (no LangGraph dependency). Steps run one after another, with bounded retries."""
import hashlib, time, traceback
from datetime import datetime, timezone
from src.agents import analysts as A
from src.data.loader import validate, quality_status
from src.finance import metrics as m

MAX_ATTEMPTS = 2
PIPELINE = [("treasury", A.treasury), ("credit", A.credit), ("forecasting", A.forecasting), ("stress", A.stress), ("research", A.research)]


def recommendations(rows, results):
    last, first, recs = rows[-1], rows[0], []
    c2d = m.cash_to_short_term_debt(last)
    if c2d is not None and c2d < 0.5:
        recs.append({"action": "Arrange committed back-up facilities / refinancing for short-term debt", "urgency": "high", "function": "Treasury",
            "rationale": f"Cash covers only {c2d:.0%} of short-term debt.", "direction": "Reduces refinancing risk",
            "quantified_impact": None, "horizon": "0-3 months", "implementation_risk": "Pricing/availability depend on lenders", "confidence": "medium", "limitations": "Maturity dates unknown"})
    d0, d1 = m.dso(first), m.dso(last)
    if d0 and d1 and d1 > d0 * 1.1:
        rel = last["revenue"] / m.DAYS_PER_QUARTER * (d1 - d0)
        recs.append({"action": "Tighten collections to recover receivable days", "urgency": "medium", "function": "Finance / Sales ops",
            "rationale": f"DSO rose from {d0:.0f} to {d1:.0f} days.", "direction": "Releases working capital",
            "quantified_impact": f"~{rel:.0f} crore if DSO returned to {d0:.0f} days (arithmetic, not a forecast)", "horizon": "1-2 quarters",
            "implementation_risk": "Customer relationship friction", "confidence": "medium", "limitations": "Assumes revenue constant"})
    fcf = m.free_cash_flow(last)
    if fcf is not None and fcf < 0:
        recs.append({"action": "Review capex phasing against negative free cash flow", "urgency": "medium", "function": "FP&A",
            "rationale": f"FCF was {fcf:.0f} crore in the latest quarter.", "direction": "Improves cash generation", "quantified_impact": None,
            "horizon": "1-2 quarters", "implementation_risk": "Growth/maintenance trade-off", "confidence": "low", "limitations": "Capex split (maintenance/growth) unknown"})
    return recs


def run_workflow(rows, fingerprint, synthetic=True, pipeline=None, evidence_pages=None):
    started, trace, results = datetime.now(timezone.utc).isoformat(), [], []
    issues = validate(rows)
    ctx = {"synthetic": synthetic, "data_errors": any(i["severity"] == "error" for i in issues), "evidence_pages": evidence_pages or []}
    trace.append({"step": "input_validation", "status": "completed" if not ctx["data_errors"] else "failed", "detail": quality_status(issues)})
    if ctx["data_errors"]:
        return {"status": "halted", "reason": "Input validation errors", "trace": trace, "issues": issues, "fingerprint": fingerprint, "started": started}
    for name, fn in (pipeline or PIPELINE):
        res, err = None, None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            t0 = time.perf_counter()
            try:
                res = fn(rows, ctx); res.execution_metadata = {"attempt": attempt, "seconds": round(time.perf_counter() - t0, 4), "mode": "deterministic", "llm_used": False}
                break
            except Exception as e:  # recorded, never silent
                err = f"{type(e).__name__}: {e}"
        if res is None:
            res = A.AgentResult(name, status="failed", summary="Agent failed after bounded retries.", warnings=[err], execution_metadata={"attempt": MAX_ATTEMPTS})
        results.append(res)
        trace.append({"step": name, "status": res.status, "attempts": res.execution_metadata.get("attempt"), "detail": res.summary})
    review = A.reviewer(results, ctx)
    trace.append({"step": "independent_review", "status": "completed", "detail": review["disposition"]})
    recs = recommendations(rows, results) if review["disposition"] != "rejected" else []
    rid = hashlib.sha256((started + fingerprint).encode()).hexdigest()[:10]
    return {"run_id": rid, "status": "completed", "started": started, "fingerprint": fingerprint, "company": rows[-1]["company_name"],
            "data_origin": "SYNTHETIC DEMONSTRATION DATA" if synthetic else "user-supplied", "period": rows[-1]["reporting_period"],
            "execution": "sequential, deterministic, no LLM", "trace": trace, "results": [r.to_dict() for r in results], "review": review,
            "recommendations": recs, "data_quality": {"status": quality_status(issues), "issues": issues},
            "synthesis_note": "Recommendations are rule-generated templates, not LLM output; human approval required."}
