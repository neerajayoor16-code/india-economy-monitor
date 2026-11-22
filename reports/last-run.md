# Update run 22 Nov 2026, 22:06 IST

Phase: **Late-stage expansion** (OECD leading index 101.45 is above 100 and rising; prices or credit show overheating signs)

## Changes

- cpi: text (template):  → CPI Retail Inflation: 6.09% YoY in Oct 2026, up from 5.54% in Sep 2026.
- wpi: text (template):  → WPI Wholesale Inflation: 12.29% YoY in Oct 2026, up from 11.39% in Sep 2026.
- unemployment: text (template):  → Unemployment Rate (PLFS): 4.9% in Oct 2026, down from 5.0% in Sep 2026.
- bank_credit: text (template):  → Bank Credit Growth: 19.54% YoY on Oct 31, 2026.
- repo_rate: text (template):  → RBI Repo Rate (Policy Rate): 5.50% on Nov 19, 2026.
- core_industries: text (template):  → Index of Core Industries (ICI): +10.9% YoY in Oct 2026, up from 8.2% in Sep 2026.
- iip: text (template):  → Index of Industrial Production (IIP): +6.7% YoY in Sep 2026, down from 7.8% in Aug 2026.
- rail_freight: text (template):  → Railway Freight Loading: +8.32% YoY in Oct 2026.
- gst: text (template):  → GST Collections: Rs. 2.31 Lakh Cr in Oct 2026, +22.9% from a year earlier.
- vehicles: text (template):  → Passenger Vehicle Sales: 5.19 Lakh Units in Oct 2026, +12.4% from a year earlier.
- gdp: text (template):  → Real GDP Growth (Reference): 7.8% YoY in Q1 FY27, down from 8.6% in Q4 FY26.
- nifty: text (template):  → Nifty 50 (Stock Market): 25,514.30 on Nov 19, 2026.
- yield_spread: text (template):  → Bond Yield Spread (10Y vs Repo): +176 bps on Nov 19, 2026.
- consumer_confidence: text (template):  → Consumer Confidence (RBI): 113.5 in Sep 2026, down from 115.4 in Jul 2026.
- industrial_outlook: text (template):  → Business Expectations (RBI): 126.3 in Q3 FY27 (expected), up from 111.1 in Q2 FY27.
- oecd_cli: text (template):  → OECD Leading Index (CLI): 101.45 in Oct 2026, up from 101.39 in Sep 2026.

## Alerts (need a human look)

- None

## Sources

- mospi_cpi: ok
- mospi_wpi: ok
- mospi_iip: ok
- mospi_unemployment: ok
- mospi_gdp: ok
- oecd_cli: ok
- rbi_home: ok
- rbi_bank_credit: ok
- rbi_consumer_confidence: no_new_release (no feed item for 'Consumer Confidence Survey'; full search skipped on light runs)
- rbi_industrial_outlook: no_new_release (no feed item for 'Industrial Outlook Survey'; full search skipped on light runs)
- pib_core_industries: no_new_release (Core industries release not in PIB's latest feed items; will retry next run)
- pib_rail_freight: no_new_release (Rail freight release not in PIB's latest feed items; will retry next run)
- gstn_gst: ok
- siam_vehicles: error (SIAM: secure connection failed (site certificate problem): SSLError)

To undo this run: revert its commit in GitHub (Commits → this commit → Revert).
