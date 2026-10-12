"""Deterministic analyst agents + independent reviewer. No LLM is used; every number comes from Python functions."""
import statistics, time
from dataclasses import dataclass, field, asdict
from src.finance import metrics as m
from src.scenarios.engine import PRESETS, run_scenario
from src.retrieval.documents import search_pages

LEVELS = ["low", "moderate", "elevated", "high"]


def level(points: int) -> str:
    return LEVELS[0 if points <= 1 else 1 if points <= 3 else 2 if points <= 5 else 3]


@dataclass
class AgentResult:
    agent_name: str
    status: str = "completed"            # completed | failed | requires_review
    summary: str = ""
    risk_level: str | None = None
    findings: list = field(default_factory=list)   # [{"id","text","metric","value","type"}] type = derived_metric|model_estimate
    metrics: dict = field(default_factory=dict)
    evidence_references: list = field(default_factory=list)
    assumptions: list = field(default_factory=list)
    uncertainty: str = ""
    limitations: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    execution_metadata: dict = field(default_factory=dict)

    def to_dict(self): return asdict(self)


def _f(i, text, metric, value, typ="derived_metric"):
    return {"id": i, "text": text, "metric": metric, "value": value, "type": typ}


def treasury(rows, ctx) -> AgentResult:
    last, s = rows[-1], m.snapshot(rows[-1])
    pts, fs = 0, []
    cr, c2d, fcf = s["current_ratio"], s["cash_to_short_term_debt"], s["free_cash_flow"]
    if cr is not None and cr < 1.0: pts += 2
    elif cr is not None and cr < 1.2: pts += 1
    if s["quick_ratio"] is not None and s["quick_ratio"] < 0.8: pts += 1
    if c2d is not None: pts += 2 if c2d < 0.5 else 1 if c2d < 1.0 else 0
    if fcf is not None and fcf < 0: pts += 1
    ocf_g = m.growth(rows, "operating_cash_flow", 4)
    if ocf_g is not None and ocf_g < -0.2: pts += 1
    fs.append(_f("T1", f"Current ratio {cr:.2f}; quick ratio {s['quick_ratio']:.2f}." if cr and s["quick_ratio"] else "Current/quick ratio unavailable.", "current_ratio", cr))
    fs.append(_f("T2", f"Cash covers {c2d:.0%} of short-term debt." if c2d is not None else "Cash/short-term debt unavailable.", "cash_to_short_term_debt", c2d))
    fs.append(_f("T3", f"Free cash flow {fcf:.0f} (OCF less capex) in latest quarter." if fcf is not None else "FCF unavailable.", "free_cash_flow", fcf))
    if ocf_g is not None: fs.append(_f("T4", f"Operating cash flow changed {ocf_g:+.0%} vs four quarters earlier.", "ocf_yoy", ocf_g))
    d0, d1 = m.dso(rows[0]), m.dso(last)
    if d0 and d1 and d1 > d0 * 1.1: pts += 1; fs.append(_f("T5", f"Receivable days rose from {d0:.0f} to {d1:.0f} over the window.", "dso", d1))
    return AgentResult("Treasury & Liquidity Analyst", summary=f"Liquidity risk {level(pts)} ({pts} rule points).", risk_level=level(pts),
        findings=fs, metrics={k: s[k] for k in ["current_ratio", "quick_ratio", "cash_to_short_term_debt", "free_cash_flow", "dso", "cash_conversion_cycle_proxy"]},
        evidence_references=[{"type": "structured_data", "ref": f"{last['reporting_period']} ({last.get('data_origin','unknown')})"}],
        assumptions=["90-day quarter", "Days metrics use revenue as denominator (COGS not in schema)"],
        uncertainty="Rule-based thresholds are generic, not sector-calibrated.", limitations=["No cash-runway estimate: burn assumptions not provided.", "Debt maturity profile unknown."])


def credit(rows, ctx) -> AgentResult:
    last, s = rows[-1], m.snapshot(rows[-1])
    pts, fs, warn = 0, [], []
    icr, d2a = s["interest_coverage"], s["debt_to_assets"]
    if icr is not None: pts += 3 if icr < 1.5 else 2 if icr < 2.5 else 1 if icr < 3.5 else 0
    else: warn.append("Interest coverage unavailable.")
    if d2a is not None and d2a > 0.35: pts += 1
    sh = m.sdiv(last.get("short_term_debt"), last.get("total_debt"))
    if sh is not None and sh > 0.4: pts += 1
    dg = m.growth(rows, "total_debt", 4)
    if dg is not None and dg > 0.1: pts += 1
    fs.append(_f("C1", f"Interest coverage {icr:.2f}x (operating profit / interest)." if icr else "Interest coverage unavailable.", "interest_coverage", icr))
    fs.append(_f("C2", f"Debt/assets {d2a:.0%}; short-term share of debt {sh:.0%}." if d2a and sh else "Leverage unavailable.", "debt_to_assets", d2a))
    if dg is not None: fs.append(_f("C3", f"Total debt grew {dg:+.0%} year on year.", "debt_growth_yoy", dg))
    return AgentResult("Credit & Solvency Analyst", summary=f"Credit risk {level(pts)} ({pts} rule points). Not a credit rating.", risk_level=level(pts),
        findings=fs, metrics={"interest_coverage": icr, "debt_to_assets": d2a, "short_term_debt_share": sh, "debt_growth_yoy": dg},
        evidence_references=[{"type": "structured_data", "ref": last["reporting_period"]}], warnings=warn,
        assumptions=["EBIT proxy = operating profit"], uncertainty="Covenant terms and maturity ladder not provided.",
        limitations=["No covenant headroom from real terms.", "Floating/fixed split unknown."])


def _fit_line(ys):
    n = len(ys); xs = list(range(n)); mx, my = statistics.mean(xs), statistics.mean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den if den else 0
    return my - b * mx, b


def forecasting(rows, ctx) -> AgentResult:
    fs, mets, warn = [], {}, []
    for key in ["revenue", "operating_cash_flow"]:
        ys = [r[key] for r in rows if r.get(key) is not None]
        if len(ys) < 6:
            warn.append(f"{key}: fewer than 6 observations; forecast skipped."); continue
        e_naive, e_lin, start = [], [], 4
        for t in range(start, len(ys)):                   # rolling origin, chronological, one-step
            tr = ys[:t]; a, b = _fit_line(tr)
            e_naive.append(abs(ys[t] - tr[-1])); e_lin.append(abs(ys[t] - (a + b * t)))
        mae_n, mae_l = statistics.mean(e_naive), statistics.mean(e_lin)
        best = "linear_trend" if mae_l < mae_n else "naive"
        a, b = _fit_line(ys); nxt = a + b * len(ys) if best == "linear_trend" else ys[-1]
        mets[key] = {"model": best, "mae_naive": mae_n, "mae_linear": mae_l, "next_quarter": nxt, "n_obs": len(ys), "n_test": len(e_naive)}
        fs.append(_f(f"F-{key}", f"{key}: {best} (MAE {min(mae_n, mae_l):.1f} vs naive {mae_n:.1f}); next-quarter estimate {nxt:.0f}.", key, nxt, "model_estimate"))
        if best == "naive": warn.append(f"{key}: trend model did not beat naive baseline.")
        chg = [ys[i] - ys[i - 1] for i in range(1, len(ys))]; med = statistics.median(chg)
        mad = statistics.median([abs(c - med) for c in chg]) or 1e-9
        for i, c in enumerate(chg, 1):
            if abs(c - med) / (1.4826 * mad) > 3.5: warn.append(f"{key}: unusual change in {rows[i]['reporting_period']}.")
    return AgentResult("Forecasting & Anomaly Analyst", status="completed" if mets else "requires_review",
        summary="One-step rolling-origin backtest vs naive baseline." if mets else "Insufficient history.", findings=fs, metrics=mets, warnings=warn,
        assumptions=["Linear trend vs last-value baseline"], uncertainty="Tiny sample (8 quarters, 4 test points): error estimates are unstable; no confidence interval claimed.",
        limitations=["No seasonality model", "Not evidence of predictive accuracy"])


def stress(rows, ctx) -> AgentResult:
    base, res = rows[-1], {}
    for name, a in PRESETS.items(): res[name] = run_scenario(base, a)
    sev, adv = res["Severe stress"], res["Adverse case"]
    pts = (2 if sev["closing_cash"] < 0 else 0) + (1 if adv["closing_cash"] < 0 else 0) + (1 if (sev["interest_coverage"] or 9) < 1.5 else 0)
    fs = [_f(f"S{i}", f"{n}: closing cash {r['closing_cash']:.0f}, ICR {r['interest_coverage']:.2f}x, funding gap {r['funding_gap']:.0f}.", "closing_cash", r["closing_cash"], "model_estimate")
          for i, (n, r) in enumerate(res.items(), 1)]
    return AgentResult("Macro & Stress-Testing Analyst", summary=f"Stress vulnerability {level(pts)}.", risk_level=level(pts), findings=fs,
        metrics={n: {k: r[k] for k in ["closing_cash", "interest_coverage", "funding_gap", "covenant_headroom_icr"]} for n, r in res.items()},
        assumptions=["Floating share of debt = 40% (assumed)", "Covenant minimum ICR 2.0x (illustrative)", "Tax, payables held constant"],
        uncertainty="Scenario outputs are conditional model estimates, not forecasts.", limitations=["One-quarter horizon", "No FX/commodity channels"])


def research(rows, ctx) -> AgentResult:
    pages = ctx.get("evidence_pages") or []
    if not pages:
        return AgentResult("Research & Evidence Agent", status="requires_review", summary="No documents were supplied to the evidence retrieval workflow.",
            warnings=["No document-sourced evidence available; findings rest on structured financial data only."],
            limitations=["Upload selectable-text PDF reports in Evidence Explorer, then rerun the assessment to include them."])
    query = "liquidity risk debt refinancing covenant cash flow receivables contingent liabilities financial risk"
    matches = search_pages(pages, query, limit=5)
    if not matches:
        return AgentResult("Research & Evidence Agent", status="requires_review", summary="Documents were available, but the risk-keyword search found no relevant passages.",
            warnings=["No matching evidence was retrieved. This does not prove the documents contain no relevant risk disclosures."],
            limitations=["Retrieval uses lexical token overlap, not semantic search; inspect the Evidence Explorer manually."])
    findings, refs = [], []
    for i, match in enumerate(matches, 1):
        excerpt = " ".join(match["excerpt"].split())[:420]
        findings.append(_f(f"R{i}", f"Potentially relevant disclosure from {match['filename']} page {match['page']}: {excerpt}",
                           "document_passage", excerpt, "evidence_statement"))
        refs.append({"type": "document_page", "filename": match["filename"], "page": match["page"],
                     "lexical_score": match["score"], "query": query})
    return AgentResult("Research & Evidence Agent", status="completed", summary=f"Retrieved {len(matches)} potentially relevant PDF page(s) using lexical keyword overlap.",
        findings=findings, evidence_references=refs,
        assumptions=["Keyword query: " + query], uncertainty="Lexical overlap indicates relevance to the query, not that a passage proves a financial risk.",
        limitations=["Search is not semantic retrieval; page text may contain extraction errors; document authenticity is not verified."])


def reviewer(results, ctx) -> dict:
    """Deterministic independent review. Reports issues; never edits agent numbers."""
    by = {r.agent_name: r for r in results}
    issues, disagreements = [], []
    for r in results:
        if r.status == "failed": issues.append({"severity": "high", "agent": r.agent_name, "issue": "Agent failed; findings unavailable."})
        for f in r.findings:
            if f["value"] is None and f["type"] != "model_estimate" and "unavailable" not in f["text"]:
                issues.append({"severity": "medium", "agent": r.agent_name, "issue": f"{f['id']} cites a metric with no value."})
    t, c, s = (by.get(k) for k in ["Treasury & Liquidity Analyst", "Credit & Solvency Analyst", "Macro & Stress-Testing Analyst"])
    if t and s and t.risk_level == "low" and s.risk_level in ("elevated", "high"):
        disagreements.append("Treasury sees low liquidity risk but stress analyst sees elevated/high vulnerability.")
    if c and t and c.risk_level and t.risk_level and abs(LEVELS.index(c.risk_level) - LEVELS.index(t.risk_level)) >= 2:
        disagreements.append("Credit and liquidity risk levels differ by two or more notches.")
    if not any(e["type"] != "structured_data" for r in results for e in r.evidence_references):
        issues.append({"severity": "medium", "agent": "Reviewer", "issue": "No document-sourced evidence; nothing is source-grounded beyond structured data."})
    fc = by.get("Forecasting & Anomaly Analyst")
    if fc and any("did not beat naive" in w for w in fc.warnings):
        issues.append({"severity": "low", "agent": fc.agent_name, "issue": "Forecast no better than baseline; do not rely on it."})
    for r in results:
        if r.metrics and not r.uncertainty: issues.append({"severity": "medium", "agent": r.agent_name, "issue": "Quantified output without stated uncertainty (false precision)."})
    if ctx.get("synthetic"): issues.append({"severity": "info", "agent": "Reviewer", "issue": "Synthetic demonstration data: not a real company."})
    if ctx.get("data_errors"): issues.append({"severity": "high", "agent": "Reviewer", "issue": "Input validation errors present."})
    high = [i for i in issues if i["severity"] == "high"]
    disposition = "rejected" if high else "conditionally_accepted" if (issues or disagreements) else "accepted"
    return {"disposition": disposition, "issues": issues, "disagreements": disagreements, "requires_human_review": True,
            "note": "Human approval is always required for recommendations in this build."}
