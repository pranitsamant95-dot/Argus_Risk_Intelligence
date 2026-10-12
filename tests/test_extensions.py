import json
from io import BytesIO
from pathlib import Path

from src.data.upload import parse_uploaded_file
from src.data.loader import load_demo
from src.orchestration.workflow import run_workflow
from src.reporting import build_pdf_report
from src.retrieval.documents import search_pages, extract_pdf_pages


def test_csv_upload_canonicalises_common_headers_and_missing_values():
    payload = b"Company,Period,Revenue,Operating Profit,Cash,Current Assets,Current Liabilities,Total Debt,Interest Expense,Operating Cash Flow\nAcme,Q1,100,12,20,50,40,15,2,8\nAcme,Q2,110,,22,52,41,16,2,9\n"
    rows = parse_uploaded_file("financials.csv", payload)
    assert rows[0]["company_name"] == "Acme"
    assert rows[0]["reporting_period"] == "Q1"
    assert rows[0]["revenue"] == 100.0
    assert rows[1]["operating_profit"] is None
    assert rows[0]["data_origin"] == "user-supplied"


def test_upload_rejects_unsupported_format():
    try:
        parse_uploaded_file("financials.pdf", b"not csv")
    except ValueError as exc:
        assert "Supported" in str(exc)
    else:
        raise AssertionError("Unsupported format should fail")


def test_pdf_report_is_generated_from_completed_run():
    rows, fingerprint = load_demo()
    run = run_workflow(rows, fingerprint, synthetic=True)
    pdf = build_pdf_report(run)
    assert pdf.startswith(b"%PDF")
    pages = extract_pdf_pages(pdf, "assessment.pdf")
    assert pages and "ARGUS" in " ".join(p["text"] for p in pages)


def test_evidence_search_retains_filename_and_page_provenance():
    pages = [
        {"filename": "annual-report.pdf", "page": 4, "text": "Liquidity risk may increase if debt refinancing becomes unavailable."},
        {"filename": "annual-report.pdf", "page": 5, "text": "The company expanded its manufacturing facility."},
    ]
    results = search_pages(pages, "liquidity risk debt refinancing", limit=3)
    assert results and results[0]["page"] == 4
    assert results[0]["filename"] == "annual-report.pdf"
    assert "refinancing" in results[0]["excerpt"]


def test_research_agent_uses_uploaded_evidence_pages():
    rows, fingerprint = load_demo()
    evidence = [{"filename": "annual-report.pdf", "page": 12,
                 "text": "Liquidity risk may arise from debt refinancing, cash flow shortfalls, covenant breaches and slower receivables collection."}]
    run = run_workflow(rows, fingerprint, synthetic=True, evidence_pages=evidence)
    research = next(a for a in run["results"] if a["agent_name"] == "Research & Evidence Agent")
    assert research["status"] == "completed"
    assert research["evidence_references"][0]["filename"] == "annual-report.pdf"
    assert research["evidence_references"][0]["page"] == 12
    assert any("No document-sourced evidence" in issue["issue"] for issue in run["review"]["issues"]) is False
