# ARGUS Architecture Notes

## Runtime flow

1. Load bundled demo data or parse a user CSV/XLSX upload.
2. Normalise basic metadata and numeric fields.
3. Validate duplicate periods, mixed units/currencies, mixed period types, missing core values, and selected accounting sanity checks.
4. Calculate financial metrics with deterministic Python functions.
5. On explicit user action, execute the sequential analyst workflow with bounded retries.
6. Apply deterministic review rules and generate rule-based recommendations only when the review does not reject the run.
7. Render results and permit JSON/PDF export.
8. Separately, upload PDFs to the Evidence Explorer for text extraction and lexical search with page provenance.

## Trust boundaries

- Uploaded financial figures are unverified input.
- Synthetic demo data is labelled as fictional.
- Model estimates are distinct from observed facts.
- LLM calls are not implemented in this build.
- Evidence Explorer results are not automatically included in the analyst workflow.
- Human review is required before acting on recommendations.

## Resource design

No external database or paid API is required. Expensive work is launched explicitly rather than during module import. Streamlit session state stores the active run and history only for the current session.
