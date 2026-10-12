# Data Dictionary

| Field | Meaning | Notes |
|---|---|---|
| company_id | Stable company identifier | User-defined where available |
| company_name | Company label | Demo company is fictional |
| sector | Sector description | Optional but recommended |
| reporting_period | Period label | Keep chronologically ordered |
| period_type | Quarterly or annual | Do not mix in one analysis |
| currency | Currency code | Keep consistent within one run |
| units | Scale such as crore or million | Keep consistent within one run |
| revenue | Reported revenue | Must match period convention |
| operating_profit | Operating profit | Used as EBIT proxy for interest coverage |
| total_assets | Total assets | Balance-sheet figure |
| cash_and_equivalents | Cash and equivalents | Balance-sheet figure |
| current_assets | Current assets | Balance-sheet figure |
| current_liabilities | Current liabilities | Balance-sheet figure |
| total_debt | Total debt | Prefer consistent definition across periods |
| short_term_debt | Short-term debt | May be a subset of total debt |
| long_term_debt | Long-term debt | Optional |
| operating_cash_flow | Cash flow from operating activities | Respect quarter/YTD reporting convention |
| capital_expenditure | Capital expenditure | Ensure sign convention is consistent; ARGUS subtracts positive capex |
| interest_expense | Interest expense | Must be positive expense amount for standard coverage calculation |
| receivables | Trade/operating receivables | Definition should be consistent |
| inventory | Inventory | Used in quick ratio and scenario model |
| payables | Trade/operating payables | Used in proxy working-capital analysis |
| source_document | Original filename or reference | Provenance field |
| data_origin | Synthetic or user-supplied | Must not be mislabelled |
