# Validation Record

## Checks executed in the build environment

- Python AST parsing: passed for all Python source and test files.
- `python -m compileall -q app.py src tests`: passed.
- `python -m pytest -q tests`: **18 passed**.
- PDF generation: a generated report was checked for a valid PDF header and its selectable text was extracted.
- Evidence retrieval: a test verified that document filename and page provenance are preserved and that retrieved evidence reaches the Research agent.
- Upload normalisation: a test verified common CSV headings and blank numeric values.

## Not verified in this environment

Streamlit is not installed in the build environment, so the interactive application was not launched here. A clean install and browser-based smoke test must still be run after installing `requirements.txt`:

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

The unit tests do not prove that the application behaves correctly in every browser, device, Streamlit version, or hosted deployment. Validate the UI locally before publishing.
