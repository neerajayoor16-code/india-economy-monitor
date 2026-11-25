# Update run 25 Nov 2026, 19:25 IST

Phase: **Late-stage expansion** (OECD leading index 101.45 is above 100 and rising; prices or credit show overheating signs)

## Changes

- repo_rate: updated: 5.50% → 5.50%
- yield_spread: updated: +176 bps → +171 bps
- nifty: updated: 25,800.60 → 25,349.65
- repo_rate: text (template):  → RBI Repo Rate (Policy Rate): 5.50% on Nov 23, 2026.
- nifty: text (template):  → Nifty 50 (Stock Market): 25,349.65 on Nov 23, 2026.
- yield_spread: text (template):  → Bond Yield Spread (10Y vs Repo): +171 bps on Nov 23, 2026.

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
- rbi_bank_credit: no_new_release (WSS extract not in RBI's latest 10 press releases; will retry next run)
- rbi_consumer_confidence: no_new_release (no feed item for 'Consumer Confidence Survey'; full search skipped on light runs)
- rbi_industrial_outlook: no_new_release (no feed item for 'Industrial Outlook Survey'; full search skipped on light runs)
- pib_core_industries: no_new_release (Core industries release not in PIB's latest feed items; will retry next run)
- pib_rail_freight: no_new_release (Rail freight release not in PIB's latest feed items; will retry next run)
- gstn_gst: ok
- siam_vehicles: error (SIAM: site is reachable again, but the page parser is not built yet. Save the press-release page as a test fixture and build parse_vehicles().)

To undo this run: revert its commit in GitHub (Commits → this commit → Revert).
