"""Lightweight, source-grounded PDF text extraction and keyword retrieval.

This deliberately uses transparent lexical ranking rather than claiming semantic RAG.
PyMuPDF is optional at import time; users receive a clear message if it is unavailable.
"""
from __future__ import annotations
import re
from collections import Counter


def extract_pdf_pages(file_bytes: bytes, filename: str) -> list[dict]:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PDF extraction requires PyMuPDF. Install the project requirements and restart.") from exc
    pages = []
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        for index, page in enumerate(doc):
            text = page.get_text("text").strip()
            if text:
                pages.append({"filename": filename, "page": index + 1, "text": text})
        doc.close()
    except Exception as exc:
        raise ValueError(f"Could not read PDF '{filename}': {exc}") from exc
    if not pages:
        raise ValueError("No selectable text was found. This may be a scanned PDF; OCR is not implemented.")
    return pages


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-zA-Z0-9]+", (text or "").lower()) if len(t) > 2]


def search_pages(pages: list[dict], query: str, limit: int = 5) -> list[dict]:
    """Rank page text by transparent token overlap; results retain exact page provenance."""
    terms = Counter(_tokens(query))
    if not terms:
        return []
    results = []
    for p in pages:
        tokens = Counter(_tokens(p.get("text", "")))
        score = sum(min(count, tokens.get(term, 0)) for term, count in terms.items())
        if score:
            text = p["text"]
            results.append({"filename": p["filename"], "page": p["page"], "score": score,
                            "excerpt": text[:1800], "text": text})
    return sorted(results, key=lambda x: (-x["score"], x["filename"], x["page"]))[:max(1, limit)]
