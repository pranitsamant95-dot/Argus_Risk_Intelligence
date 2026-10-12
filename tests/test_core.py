import json, math, pytest
from dataclasses import replace
from src.data.loader import load_demo, validate, parse_csv_text
from src.finance import metrics as m
from src.scenarios.engine import PRESETS, Assumptions, run_scenario, sensitivity
from src.agents import analysts as A
from src.orchestration.workflow import run_workflow, PIPELINE, MAX_ATTEMPTS

ROWS, FP = load_demo()
LAST = ROWS[-1]


def test_ratios_hand_calculated():
    r = {"current_assets": 200, "current_liabilities": 100, "inventory": 50, "operating_profit": 30, "interest_expense": 10}
    assert m.current_ratio(r) == 2.0 and m.quick_ratio(r) == 1.5 and m.interest_coverage(r) == 3.0
    assert math.isclose(m.current_ratio(LAST), 1880 / 1560)


def test_missing_and_zero_denominators_are_undefined_not_zero():
    assert m.sdiv(5, 0) is None and m.sdiv(5, -2) is None and m.sdiv(None, 3) is None
    assert m.interest_coverage({"operating_profit": 10, "interest_expense": 0}) is None
    assert m.free_cash_flow({"operating_cash_flow": 5}) is None


def test_missing_csv_values_stay_none():
    rows = parse_csv_text("company_id,reporting_period,revenue,operating_profit\nX,Q1,100,\n")
    assert rows[0]["operating_profit"] is None


def test_validation_flags_duplicates_and_mixed_period_types():
    bad = [dict(LAST), dict(LAST, period_type="annual")]
    msgs = " ".join(i["message"] for i in validate(bad))
    assert "Duplicate" in msgs and "Annual and quarterly" in msgs


def test_base_case_matches_observed_cash_arithmetic():
    b = run_scenario(LAST, PRESETS["Base case"])
    assert math.isclose(b["closing_cash"], 270 + 70 - 110) and math.isclose(b["operating_cash_flow"], 70)


def test_scenario_ordering_and_rate_shock_logic():
    base, adv, sev = (run_scenario(LAST, PRESETS[k]) for k in ["Base case", "Adverse case", "Severe stress"])
    assert base["closing_cash"] > adv["closing_cash"] > sev["closing_cash"]
    assert run_scenario(LAST, Assumptions(rate_shock_bps=300, floating_share=0))["interest_expense"] == LAST["interest_expense"]
    assert run_scenario(LAST, Assumptions(rate_shock_bps=300))["interest_expense"] > LAST["interest_expense"]


def test_extreme_or_invalid_assumptions_rejected():
    with pytest.raises(ValueError): run_scenario(LAST, Assumptions(revenue_change=-1.5))
    with pytest.raises(ValueError): run_scenario(dict(LAST, receivables=None), Assumptions())
    assert run_scenario(LAST, Assumptions(revenue_change=-0.9))["revenue"] > 0


def test_sensitivity_signs():
    s = sensitivity(LAST)
    assert all(v["delta_closing_cash"] < 0 for v in s.values())


def test_agent_schema_and_workflow_without_api_key():
    run = run_workflow(ROWS, FP)
    assert run["status"] == "completed" and run["execution"].startswith("sequential")
    req = {"agent_name", "status", "summary", "findings", "metrics", "evidence_references", "assumptions", "uncertainty", "limitations", "warnings", "execution_metadata"}
    for r in run["results"]:
        assert req <= set(r) and r["execution_metadata"]["llm_used"] is False
    assert run["review"]["disposition"] in {"accepted", "conditionally_accepted"}
    assert "SYNTHETIC" in run["data_origin"] and json.dumps(run)  # JSON-serialisable


def test_reviewer_flags_no_evidence_and_synthetic_and_rejects_failed_agent():
    run = run_workflow(ROWS, FP)
    msgs = " ".join(i["issue"] for i in run["review"]["issues"])
    assert "No document-sourced evidence" in msgs and "Synthetic" in msgs

    def boom(rows, ctx): raise RuntimeError("x")
    failed = run_workflow(ROWS, FP, pipeline=PIPELINE + [("broken", boom)])
    assert any(r["status"] == "failed" for r in failed["results"]) and failed["review"]["disposition"] == "rejected"
    assert failed["recommendations"] == []


def test_retries_are_bounded_and_one_failure_does_not_stop_run():
    calls = {"n": 0}
    def flaky(rows, ctx): calls["n"] += 1; raise ValueError("nope")
    run = run_workflow(ROWS, FP, pipeline=[("flaky", flaky)] + PIPELINE)
    assert calls["n"] == MAX_ATTEMPTS and len(run["results"]) == len(PIPELINE) + 1


def test_reviewer_catches_valueless_metric_claim():
    bad = A.AgentResult("Treasury & Liquidity Analyst", findings=[{"id": "X", "text": "claim", "metric": "m", "value": None, "type": "derived_metric"}], uncertainty="u")
    assert any("no value" in i["issue"] for i in A.reviewer([bad], {})["issues"])


def test_validation_errors_halt_workflow():
    run = run_workflow([dict(LAST), dict(LAST)], FP)
    assert run["status"] == "halted"
