"""ARGUS | Enterprise Financial Risk Intelligence. Run with: streamlit run app.py"""
from __future__ import annotations
import hashlib, json
from dataclasses import asdict
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.data.loader import load_demo, validate, quality_status
from src.data.upload import parse_uploaded_file
from src.finance import metrics as m
from src.scenarios.engine import PRESETS, Assumptions, run_scenario, sensitivity
from src.orchestration.workflow import run_workflow
from src.reporting import build_pdf_report
from src.retrieval.documents import extract_pdf_pages, search_pages

st.set_page_config(page_title="ARGUS | Risk Intelligence", page_icon="◆", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
:root { --ink:#172B4D; --muted:#68778D; --line:#DFE6EE; --paper:#F5F7FA; --white:#FFFFFF; --blue:#2457C5; --teal:#087E8B; --amber:#C77716; --coral:#C94C4C; }
.block-container { padding-top:1.15rem; padding-bottom:2.4rem; max-width:1580px; }
[data-testid="stAppViewContainer"] { background:var(--paper); }
[data-testid="stHeader"] { background:rgba(245,247,250,.92); }
[data-testid="stSidebar"] { display:none; }
[data-testid="stSidebarCollapsedControl"] { display:none; }
[data-testid="stMetric"] { background:#FFFFFF; border:1px solid var(--line); border-radius:8px; padding:14px 16px; box-shadow:0 1px 2px rgba(20,42,72,.035); }
[data-testid="stMetricLabel"] { color:var(--muted); font-size:.82rem; }
[data-testid="stMetricValue"] { color:var(--ink); font-weight:700; }
h1,h2,h3,h4 { color:var(--ink); letter-spacing:-.025em; }
p, label, [data-testid="stMarkdownContainer"] { color:#26364F; }
hr { border-color:var(--line); }
.stTabs [data-baseweb="tab-list"] { gap:5px; background:#E9EEF5; padding:5px; border-radius:9px; }
.stTabs [data-baseweb="tab"] { background:transparent; border-radius:6px; padding:9px 13px; color:#52637B; border:1px solid transparent; }
.stTabs [aria-selected="true"] { background:#FFFFFF !important; color:var(--blue) !important; border-color:#D9E2F0 !important; box-shadow:0 1px 2px rgba(20,42,72,.06); }
div[data-testid="stExpander"] { border:1px solid var(--line); border-radius:8px; background:#FFFFFF; }
div[data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:8px; overflow:hidden; }
.stButton > button[kind="primary"] { background:var(--blue); border:1px solid var(--blue); color:#FFFFFF; border-radius:7px; font-weight:650; min-height:2.7rem; }
.stButton > button[kind="secondary"] { border:1px solid #CFD9E6; color:var(--ink); background:#FFFFFF; border-radius:7px; }
.stDownloadButton > button { border-radius:7px; border-color:#CFD9E6; }
.argus-brand { font-size:1.02rem; font-weight:800; letter-spacing:.09em; color:var(--ink); }
.argus-kicker { font-size:.72rem; font-weight:750; letter-spacing:.13em; text-transform:uppercase; color:var(--teal); }
.argus-page-title { font-size:2.05rem; line-height:1.15; font-weight:760; letter-spacing:-.045em; color:var(--ink); margin:.35rem 0 .2rem 0; }
.argus-subtitle { color:var(--muted); font-size:.96rem; margin-bottom:1.15rem; }
.argus-panel { background:#FFFFFF; border:1px solid var(--line); border-radius:10px; padding:15px 17px; }
.argus-chip { display:inline-block; border-radius:4px; padding:5px 8px; font-size:.72rem; font-weight:750; letter-spacing:.04em; background:#E4F3F3; color:#08727D; }
.argus-muted { color:var(--muted); font-size:.84rem; }
@media (max-width: 800px) { .block-container { padding-left:1rem; padding-right:1rem; } .argus-page-title { font-size:1.6rem; } }
</style>
""", unsafe_allow_html=True)
@st.cache_data
def cached_demo():
    rows, fingerprint = load_demo()
    return rows, fingerprint

@st.cache_data(show_spinner=False)
def cached_pdf_pages(file_bytes: bytes, filename: str):
    return extract_pdf_pages(file_bytes, filename)

def fmt(x, digits=2, suffix=""):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "n/a"
    try: return f"{float(x):,.{digits}f}{suffix}"
    except (ValueError, TypeError): return str(x)

def safe_json(value):
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)

def make_fingerprint(rows):
    return hashlib.sha256(safe_json(rows).encode("utf-8")).hexdigest()[:16]

def clean_df(rows):
    return pd.DataFrame(rows).replace({float("inf"): None, float("-inf"): None})

if "history" not in st.session_state: st.session_state.history = []
if "run" not in st.session_state: st.session_state.run = None
if "evidence_pages" not in st.session_state: st.session_state.evidence_pages = []
if "dataset_rows" not in st.session_state:
    demo_rows, demo_fp = cached_demo()
    st.session_state.dataset_rows = demo_rows
    st.session_state.dataset_fp = demo_fp
    st.session_state.dataset_synthetic = True
    st.session_state.dataset_label = "Synthetic demonstration company"
for k, v in asdict(PRESETS["Base case"]).items(): st.session_state.setdefault(f"a_{k}", v)

# Product header and workspace controls live in the main canvas; no sidebar is used.
head_l, head_r = st.columns([3, 1])
with head_l:
    st.markdown('<div class="argus-brand">◆ ARGUS <span style="color:#9AA8BA;font-weight:500;letter-spacing:0"> / FINANCIAL RISK INTELLIGENCE</span></div>', unsafe_allow_html=True)
with head_r:
    st.markdown('<div style="text-align:right;padding-top:3px"><span class="argus-chip">CORPORATE RISK WORKSPACE</span></div>', unsafe_allow_html=True)
st.markdown("<hr style='margin:.8rem 0 1.1rem 0'>", unsafe_allow_html=True)

control_l, control_m, control_r = st.columns([1.15, 2.5, 1.1], vertical_alignment="center")
with control_l:
    st.markdown('<div class="argus-kicker">Data workspace</div>', unsafe_allow_html=True)
    mode = st.radio("Data source", ["Demonstration data", "Upload financials"], horizontal=True, label_visibility="collapsed", key="data_mode")
with control_m:
    if mode == "Demonstration data":
        rows, fp = cached_demo()
        st.session_state.dataset_rows, st.session_state.dataset_fp = rows, fp
        st.session_state.dataset_synthetic = True
        st.session_state.dataset_label = "Synthetic demonstration company"
        st.markdown('<div class="argus-panel"><div class="argus-kicker">Active dataset</div><strong>Synthetic Industries Ltd. (Fictional)</strong><div class="argus-muted">Bundled demonstration data · INR crore · Not actual company disclosures</div></div>', unsafe_allow_html=True)
    else:
        upload = st.file_uploader("Upload CSV or Excel financial statements", type=["csv", "xlsx", "xls"], help="Use one row per reporting period. Include company, reporting period, revenue, cash, debt and other available financial fields.")
        if upload is not None:
            try:
                new_rows = parse_uploaded_file(upload.name, upload.getvalue())
                new_fp = make_fingerprint(new_rows)
                if new_fp != st.session_state.dataset_fp or st.session_state.dataset_synthetic:
                    st.session_state.dataset_rows, st.session_state.dataset_fp = new_rows, new_fp
                    st.session_state.dataset_synthetic = False
                    st.session_state.dataset_label = upload.name
                    st.session_state.run = None
                st.success(f"Loaded {len(new_rows)} reporting periods from {upload.name}")
            except Exception as exc:
                st.error(f"Upload could not be loaded: {exc}")
        elif st.session_state.dataset_synthetic:
            st.caption("Choose a CSV/XLSX file to switch from the bundled demo to your own financial data.")
with control_r:
    st.markdown('<div class="argus-kicker">Workflow</div>', unsafe_allow_html=True)
    if st.button("Run risk assessment", type="primary", use_container_width=True):
        active_rows = st.session_state.dataset_rows
        st.session_state.run = run_workflow(active_rows, st.session_state.dataset_fp, synthetic=st.session_state.dataset_synthetic, evidence_pages=st.session_state.get("evidence_pages", []))
        active_run = st.session_state.run
        st.session_state.history.append({"run_id": active_run.get("run_id", "not generated"), "started": active_run.get("started"), "disposition": active_run.get("review", {}).get("disposition", active_run.get("status")), "dataset": st.session_state.dataset_label})

rows = st.session_state.dataset_rows
fp = st.session_state.dataset_fp
synthetic = st.session_state.dataset_synthetic
issues = validate(rows)
last = rows[-1] if rows else {}
st.markdown("<hr style='margin:1rem 0 1.15rem 0'>", unsafe_allow_html=True)

rows = st.session_state.dataset_rows
fp = st.session_state.dataset_fp
synthetic = st.session_state.dataset_synthetic
last = rows[-1] if rows else {}
snap = m.snapshot(last) if last else {}
run = st.session_state.run

company_title = last.get("company_name", "Company workspace")
period_title = last.get("reporting_period", "Reporting period unavailable")
st.markdown(f'<div class="argus-page-title">{company_title}</div>', unsafe_allow_html=True)
st.markdown(f'<div class="argus-subtitle">Risk position and financial performance <span style="color:#A1ADBC">/</span> {period_title} <span style="color:#A1ADBC">/</span> {"Synthetic demonstration data" if synthetic else "User-supplied dataset"}</div>', unsafe_allow_html=True)
if synthetic:
    st.warning("DEMONSTRATION DATA · Figures shown are fictional and are provided to demonstrate the platform.")
else:
    st.info("USER DATASET · Figures were supplied by the user and have not been independently verified against official filings.")

tabs = st.tabs(["Overview", "Financials", "Stress testing", "Agent review", "Evidence", "Decision brief", "Audit trail"])

# 1. Executive overview
with tabs[0]:
    top_l, top_r = st.columns([3, 1])
    with top_l:
        st.markdown("### Executive risk overview")
        st.write(f"**{last.get('company_name', 'Company')}** · {last.get('sector', 'Sector not specified')} · Reporting period: **{last.get('reporting_period', 'n/a')}**")
    with top_r:
        if run and run.get("status") == "completed":
            st.metric("Latest review", run.get("review", {}).get("disposition", "n/a").replace("_", " ").title())
        else: st.metric("Assessment status", "Not run")
    kpis = st.columns(6)
    kpis[0].metric("Current ratio", fmt(snap.get("current_ratio")))
    kpis[1].metric("Quick ratio", fmt(snap.get("quick_ratio")))
    kpis[2].metric("Interest coverage", fmt(snap.get("interest_coverage"), 2, "x"))
    kpis[3].metric("Operating margin", fmt(snap.get("operating_margin") * 100 if snap.get("operating_margin") is not None else None, 1, "%"))
    kpis[4].metric("Cash / ST debt", fmt(snap.get("cash_to_short_term_debt") * 100 if snap.get("cash_to_short_term_debt") is not None else None, 0, "%"))
    kpis[5].metric("Free cash flow", fmt(snap.get("free_cash_flow"), 0))
    st.divider()
    df = clean_df(rows)
    df["current_ratio"] = [m.current_ratio(r) for r in rows]
    df["interest_coverage"] = [m.interest_coverage(r) for r in rows]
    df["cash_to_short_term_debt"] = [m.cash_to_short_term_debt(r) for r in rows]
    df["debt_to_assets"] = [m.debt_to_assets(r) for r in rows]
    c1, c2 = st.columns(2)
    with c1:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["reporting_period"], y=df["current_ratio"], name="Current ratio", mode="lines+markers"))
        fig.add_trace(go.Scatter(x=df["reporting_period"], y=df["cash_to_short_term_debt"], name="Cash / ST debt", mode="lines+markers"))
        fig.update_layout(title="Liquidity indicators", height=320, margin=dict(t=50,b=20), legend=dict(orientation="h", y=-.22), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#FFFFFF")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["reporting_period"], y=df["interest_coverage"], name="Interest coverage", mode="lines+markers"))
        fig.add_trace(go.Scatter(x=df["reporting_period"], y=df["debt_to_assets"], name="Debt / assets", mode="lines+markers", yaxis="y2"))
        fig.update_layout(title="Solvency indicators", height=320, margin=dict(t=50,b=20), legend=dict(orientation="h", y=-.22), yaxis2=dict(overlaying="y", side="right"), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#FFFFFF")
        st.plotly_chart(fig, use_container_width=True)
    st.markdown("### Scenario snapshot")
    try:
        scenario_rows = []
        for name, assumptions in PRESETS.items():
            result = run_scenario(last, assumptions)
            scenario_rows.append({"Scenario": name, "Revenue": result["revenue"], "Operating profit": result["operating_profit"], "Closing cash": result["closing_cash"], "Funding gap": result["funding_gap"], "Interest coverage": result["interest_coverage"]})
        st.dataframe(pd.DataFrame(scenario_rows).round(2), use_container_width=True, hide_index=True)
        st.caption("One-quarter scenario estimates conditional on documented assumptions. These are not forecasts.")
    except ValueError as exc:
        st.info(f"Scenario analysis is unavailable for this dataset: {exc}")
    st.markdown("### Priority findings")
    if run and run.get("status") == "completed":
        register = [{"Agent": a.get("agent_name"), "Risk level": a.get("risk_level"), "Finding": f.get("text"), "Basis": f.get("type")} for a in run.get("results", []) for f in a.get("findings", [])]
        if register: st.dataframe(pd.DataFrame(register), use_container_width=True, hide_index=True)
        else: st.caption("No findings returned.")
    else:
        st.info("Run a risk assessment using the action in the workspace toolbar to populate agent findings and the risk register.")

# 2. Company analysis
with tabs[1]:
    st.markdown("### Financial statements and ratios")
    st.caption("All metrics are calculated from the currently selected dataset. Missing values remain unavailable rather than being imputed as zero.")
    table = clean_df(rows)
    metric_map = {"Current ratio": m.current_ratio, "Quick ratio": m.quick_ratio, "Interest coverage": m.interest_coverage, "Operating margin": m.operating_margin, "Debt / assets": m.debt_to_assets, "Cash / short-term debt": m.cash_to_short_term_debt, "Free cash flow": m.free_cash_flow, "DSO": m.dso, "DIO (revenue proxy)": m.dio, "DPO (revenue proxy)": m.dpo, "Cash conversion cycle (proxy)": m.cash_conversion_cycle}
    selected_metrics = st.multiselect("Metrics to display", list(metric_map), default=["Current ratio", "Interest coverage", "Operating margin", "Free cash flow"])
    for name in selected_metrics: table[name] = [metric_map[name](r) for r in rows]
    columns = [c for c in ["company_name", "reporting_period", "period_type", "currency", "units", "revenue", "operating_profit", "cash_and_equivalents", "total_debt", "operating_cash_flow"] if c in table.columns] + selected_metrics
    st.dataframe(table[columns], use_container_width=True, hide_index=True)
    st.download_button("Download normalised financial data (CSV)", table.to_csv(index=False).encode("utf-8"), "argus_normalised_financials.csv", "text/csv")
    with st.expander("Data-quality findings", expanded=True):
        if issues:
            st.dataframe(pd.DataFrame(issues), use_container_width=True, hide_index=True)
        else: st.success("No issues were detected by the current internal validation checks. This is not independent verification.")
    st.markdown("### Metric definitions")
    st.markdown("- **Current ratio:** current assets / current liabilities.\n- **Quick ratio:** (current assets − inventory) / current liabilities.\n- **Interest coverage:** operating profit / interest expense.\n- **Free cash flow proxy:** operating cash flow − capital expenditure.\n- **DSO/DIO/DPO:** the current implementation uses revenue as a denominator for comparability; DIO and DPO are proxies, not conventional COGS-based calculations.")

# 3. Stress lab
with tabs[2]:
    st.markdown("### Interactive stress-testing laboratory")
    st.caption("Change assumptions to see a transparent one-quarter model response. Assumptions are not automatically inferred from actual debt contracts.")
    preset_cols = st.columns(4)
    def set_preset(name):
        for key, value in asdict(PRESETS[name]).items(): st.session_state[f"a_{key}"] = value
    for col, name in zip(preset_cols[:3], PRESETS): col.button(name, on_click=set_preset, args=(name,), use_container_width=True)
    preset_cols[3].button("Reset", on_click=set_preset, args=("Base case",), use_container_width=True)
    left, right = st.columns(2)
    left.slider("Revenue change", -0.5, 0.3, key="a_revenue_change", step=0.01, format="%.2f")
    left.slider("Margin compression (percentage points as fraction)", 0.0, 0.15, key="a_margin_compression", step=0.005, format="%.3f")
    left.slider("Operating cost reduction (share of cost base)", 0.0, 0.2, key="a_opex_cut", step=0.01)
    left.slider("Additional collection delay (days)", 0, 60, key="a_collection_delay_days")
    right.slider("Interest-rate shock (basis points)", 0, 600, key="a_rate_shock_bps", step=25)
    right.slider("Assumed floating-rate debt share", 0.0, 1.0, key="a_floating_share", step=0.05, help="Use a documented debt split when available. Otherwise this is an assumption.")
    right.slider("Inventory build", 0.0, 0.5, key="a_inventory_build", step=0.01)
    right.slider("Short-term debt not refinanced", 0.0, 1.0, key="a_refinancing_shortfall", step=0.05)
    assumptions = Assumptions(**{key: st.session_state[f"a_{key}"] for key in asdict(Assumptions())})
    try:
        base_s = run_scenario(last, Assumptions())
        custom_s = run_scenario(last, assumptions)
        compare_keys = ["revenue", "operating_profit", "interest_expense", "operating_cash_flow", "closing_cash", "liquidity_buffer_required", "funding_gap", "interest_coverage", "covenant_headroom_icr"]
        comparison = pd.DataFrame({"Base case": {k: base_s[k] for k in compare_keys}, "Current scenario": {k: custom_s[k] for k in compare_keys}})
        st.dataframe(comparison.round(3), use_container_width=True)
        fig = go.Figure([go.Bar(name="Base", x=["Operating profit", "Operating cash flow", "Closing cash"], y=[base_s["operating_profit"], base_s["operating_cash_flow"], base_s["closing_cash"]]), go.Bar(name="Current scenario", x=["Operating profit", "Operating cash flow", "Closing cash"], y=[custom_s["operating_profit"], custom_s["operating_cash_flow"], custom_s["closing_cash"]])])
        fig.update_layout(barmode="group", height=320, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#FFFFFF")
        st.plotly_chart(fig, use_container_width=True)
        if custom_s["funding_gap"] > 0: st.error(f"Estimated funding gap versus the model's 30-day operating-cost buffer: {custom_s['funding_gap']:,.2f} {last.get('currency','INR')} {last.get('units','crore')}.")
        else: st.success("No gap versus the model's 30-day operating-cost buffer under the selected assumptions. This does not guarantee adequate liquidity.")
        sens = sensitivity(last, assumptions)
        sens_df = pd.DataFrame({"Shock": {k: v["shock"] for k,v in sens.items()}, "Change in closing cash": {k: v["delta_closing_cash"] for k,v in sens.items()}}).sort_values("Change in closing cash")
        st.markdown("#### One-at-a-time sensitivity")
        st.bar_chart(sens_df["Change in closing cash"])
        st.dataframe(sens_df, use_container_width=True)
        st.download_button("Download scenario JSON", safe_json(custom_s).encode("utf-8"), "argus_scenario.json", "application/json")
    except (ValueError, KeyError, TypeError) as exc:
        st.error(f"Scenario unavailable: {exc}")
    with st.expander("Model assumptions and limitations"):
        st.markdown("The scenario engine models one quarter. Floating-rate share and covenant minimum are assumptions unless supplied from real debt documentation. Taxes, payables and several other items are held constant. Results are conditional model estimates, not forecasts, covenant determinations or audited cash-flow projections.")

# 4. Agent investigation
with tabs[3]:
    st.markdown("### Agent investigation")
    if not run: st.info("Run a risk assessment using the action in the workspace toolbar.")
    elif run.get("status") == "halted": st.error(run.get("reason", "Workflow halted")); st.json(run.get("issues", []))
    else:
        st.caption(f"Run `{run.get('run_id')}` · {run.get('execution', 'execution metadata unavailable')}. The current workflow is sequential, not parallel.")
        st.dataframe(pd.DataFrame(run.get("trace", [])), use_container_width=True, hide_index=True)
        for agent in run.get("results", []):
            with st.expander(f"{agent.get('agent_name')} · {agent.get('status')} · {agent.get('risk_level') or 'risk unclassified'}"):
                st.write(agent.get("summary", "No summary."))
                for finding in agent.get("findings", []): st.markdown(f"- **{finding.get('type','finding')}**: {finding.get('text','')}")
                st.caption("Uncertainty: " + str(agent.get("uncertainty", "Not stated")))
                st.json({k: agent.get(k) for k in ["metrics", "evidence_references", "assumptions", "limitations", "warnings", "execution_metadata"]}, expanded=False)
        review = run.get("review", {})
        st.markdown(f"#### Independent review: {str(review.get('disposition','unknown')).replace('_',' ').title()}")
        for disagreement in review.get("disagreements", []): st.warning("Disagreement: " + disagreement)
        if review.get("issues"): st.dataframe(pd.DataFrame(review["issues"]), use_container_width=True, hide_index=True)

# 5. Evidence explorer
with tabs[4]:
    st.markdown("### Evidence explorer")
    st.write("Upload annual reports, quarterly filings or other financial PDFs. ARGUS extracts selectable text and searches for relevant passages. It does not perform OCR on scanned documents.")
    pdfs = st.file_uploader("Upload PDF documents", type=["pdf"], accept_multiple_files=True, key="evidence_upload")
    pages = []
    if pdfs:
        for file in pdfs:
            try: pages.extend(cached_pdf_pages(file.getvalue(), file.name))
            except Exception as exc: st.error(f"{file.name}: {exc}")
        if pages:
            st.session_state.evidence_pages = pages
            st.success(f"Extracted selectable text from {len(pages)} pages across {len(pdfs)} uploaded PDF(s). These pages will be included in the next risk assessment.")
            query = st.text_input("Search documents", placeholder="e.g. liquidity risk, debt maturity, contingent liabilities")
            if query:
                matches = search_pages(pages, query, limit=8)
                if not matches: st.info("No keyword-overlap results found. Try a broader query.")
                for match in matches:
                    with st.expander(f"{match['filename']} · page {match['page']} · lexical score {match['score']}"):
                        st.text(match["excerpt"])
                        st.caption("Source: uploaded PDF; page number is from the uploaded file. Search ranking is lexical token overlap, not semantic similarity.")
            st.download_button("Download extracted page index (JSON)", safe_json(pages).encode("utf-8"), "argus_extracted_evidence.json", "application/json")
    else:
        if st.session_state.evidence_pages:
            st.info(f"{len(st.session_state.evidence_pages)} evidence pages remain loaded in this session for the next assessment.")
        else:
            st.info("No documents uploaded. Document-sourced findings will remain unavailable until evidence is supplied.")
    st.markdown("#### Evidence standards")
    st.markdown("- Search results quote extracted document text and retain filename/page provenance.\n- The current search ranks keyword overlap; it is not an embedding-based vector search.\n- Scanned PDFs without selectable text require OCR, which is not included.\n- Uploading a document does not automatically verify its authenticity or link it to the selected company's figures.")

# 6. Reports
with tabs[5]:
    st.markdown("### Decision brief and exports")
    if run and run.get("status") == "completed":
        st.write(f"**{run.get('company')}** · {run.get('period')} · {run.get('data_origin')} · review: **{run.get('review',{}).get('disposition')}**")
        st.caption(run.get("synthesis_note", "Recommendations require human review."))
        recs = run.get("recommendations", [])
        if recs:
            for rec in recs:
                with st.expander(f"{str(rec.get('urgency','')).upper()} · {rec.get('action')}"):
                    st.write(rec.get("rationale")); st.write("**Expected direction:** " + str(rec.get("direction")))
                    st.write("**Estimated impact:** " + str(rec.get("quantified_impact")))
                    st.write("**Horizon:** " + str(rec.get("horizon")))
                    st.write("**Limitations:** " + str(rec.get("limitations")))
        else: st.info("No rule-based recommendations were issued for this run.")
        st.download_button("Download complete assessment (JSON)", safe_json(run).encode("utf-8"), f"argus_run_{run.get('run_id','assessment')}.json", "application/json")
        try:
            pdf_bytes = build_pdf_report(run)
            st.download_button("Download risk assessment (PDF)", pdf_bytes, f"argus_risk_report_{run.get('run_id','assessment')}.pdf", "application/pdf")
        except Exception as exc: st.error(f"PDF report generation failed: {exc}")
    else:
        st.info("Run a completed assessment first. Exports are generated from the stored run results, not from a mock report.")

# 7. Audit and validation
with tabs[6]:
    st.markdown("### Audit trail and validation")
    st.caption("This build keeps run history in the current Streamlit session only. It does not provide durable multi-user persistence.")
    if st.session_state.history:
        st.dataframe(pd.DataFrame(st.session_state.history), use_container_width=True, hide_index=True)
        st.download_button("Download session audit history (JSON)", safe_json(st.session_state.history).encode("utf-8"), "argus_audit_history.json", "application/json")
    else: st.info("No assessment runs in this session yet.")
    st.markdown("#### Input validation")
    st.write(f"Dataset fingerprint: `{fp}`")
    st.write(f"Internal data-quality status: **{quality_status(issues)}**")
    if issues: st.dataframe(pd.DataFrame(issues), use_container_width=True, hide_index=True)
    else: st.success("No issues detected by the implemented checks. This does not establish source authenticity or accounting correctness.")
    st.markdown("#### Model validation")
    st.write("Forecast backtesting, when enough historical observations are available, runs as part of the explicit risk-assessment action. A separate large-scale validation suite is not run automatically at app startup.")
    if run and run.get("status") == "completed":
        forecast_agent = next((a for a in run.get("results", []) if a.get("agent_name") == "Forecasting & Anomaly Analyst"), None)
        if forecast_agent:
            st.json({"status": forecast_agent.get("status"), "metrics": forecast_agent.get("metrics", {}), "warnings": forecast_agent.get("warnings", []), "limitations": forecast_agent.get("limitations", [])})
    st.markdown("#### Download reproducibility bundle")
    bundle = {"dataset_fingerprint": fp, "dataset_origin": "synthetic" if synthetic else "user-supplied", "validation_issues": issues, "latest_run": run, "history": st.session_state.history}
    st.download_button("Download audit bundle (JSON)", safe_json(bundle).encode("utf-8"), "argus_audit_bundle.json", "application/json")

st.divider()
st.caption("ARGUS is a financial decision-support demonstration. It is not an audit, credit rating, investment recommendation, or substitute for professional review.")
