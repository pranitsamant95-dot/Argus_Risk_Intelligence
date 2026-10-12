# Financial Methodology and Assumptions

## Metric definitions

- Current ratio = current assets / current liabilities.
- Quick ratio = (current assets - inventory) / current liabilities.
- Interest coverage = operating profit / interest expense.
- Debt/assets = total debt / total assets.
- Free cash flow proxy = operating cash flow - capital expenditure.
- DSO = receivables / quarterly revenue * 90 days.
- DIO and DPO are revenue-denominator proxies in this build; standard formulations usually use cost of goods sold or purchases where available.

A metric with missing inputs or an invalid denominator is reported as unavailable rather than zero. These ratios are not sector-calibrated ratings.

## Scenario engine

The stress engine models one quarter. Revenue changes are applied to base revenue. Operating profit uses base operating margin adjusted for margin compression, with a separate operating-cost reduction assumption. The interest-rate shock reprices only an assumed floating-rate share of total debt. Receivables delay and inventory build consume working capital. Taxes, payables and several other effects are held constant. A refinancing shortfall is modelled as an outflow against short-term debt. The funding gap compares closing cash against a simplified 30-day operating-cost buffer.

The default 40% floating-rate share and 2.0x covenant minimum are illustrative assumptions, not sourced contract terms. Scenario outputs are conditional estimates, not forecasts.

## Risk classification

Agent risk levels use generic rule points. They are not calibrated probabilities of default, regulatory classifications, or formal credit ratings. Thresholds should be reviewed for sector and company context before any operational use.

## Forecasting

The forecasting agent compares a linear trend with a last-observation baseline using a small rolling-origin evaluation. When there are too few observations, it skips forecasting. A small number of test observations makes error estimates unstable; no claim of predictive superiority should be made without broader out-of-sample validation.
