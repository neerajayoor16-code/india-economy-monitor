# India Economic Health Monitor

A plain-English dashboard of India's business cycle. 16 official indicators update automatically from MoSPI, RBI, OECD, PIB and GSTN.

## How it works

1. A GitHub workflow runs every 30 minutes on weekdays (09:30 to 18:30 IST) and once a day at 18:45 IST.
2. `fetchers/` read each official source. A source that fails keeps its last number.
3. `scripts/rules.py` checks each new number (sane range, not older, no sudden jump) and sets the Good / Watch closely / Warning sign signals and the economic phase.
4. `scripts/write_text.py` writes the card text with Claude, if `ANTHROPIC_API_KEY` is set. Text goes live only after three automatic checks; otherwise plain fill-in text is used.
5. `scripts/build.py` builds the site into `docs/`. The workflow commits it, and GitHub Pages publishes it.
6. Each publish adds a report to the "Update log" issue. Problems go to the "Data alerts" issue. To undo an update: Actions → "Revert an update" → paste the commit ID.

## One-time setup (owner)

1. **Merge this work into `main`.** Scheduled workflows only run on the default branch.
2. **Turn on GitHub Pages:** Settings → Pages → Source: "Deploy from a branch" → Branch: `main`, folder: `/docs` → Save.
3. **Add the AI key (optional, about $10 a month):** Settings → Secrets and variables → Actions → New repository secret → Name `ANTHROPIC_API_KEY`. Without it, cards use plain fill-in text.
4. **Your own domain (optional):** Settings → Pages → Custom domain. Then change `base_url` in `data/site_config.json`.
5. **About page:** fill in `owner_name`, `owner_bio` and `contact_email` in `data/site_config.json`. Google weighs who runs a finance site.
6. **Analytics:** paste your analytics snippet into `analytics_html` in `data/site_config.json`.

## Run it yourself

```bash
pip install -r requirements.txt
python -m pytest -q
python scripts/update.py --no-ai     # fetch, check, rebuild (exit 2 = alerts to read)
python scripts/build.py              # rebuild from saved data only
```

## Known gaps

- **Vehicle sales (SIAM):** SIAM's website certificate expired on 21 Nov 2026. The card shows a value entered by hand until the site is fixed and a parser is built (`fetchers/siam.py`).
- **Nifty 50 signal:** needs about 3 months of daily history before it judges the trend. Until then it shows "Watch closely".
- **GST report file name:** GSTN changes the PDF name from month to month. If none of the known patterns works, an alert asks for the new pattern (`fetchers/gst.py`).
- **Release dates** in "What to watch next" come from `data/calendar.json`. Add new official dates when the alert says fewer than 4 remain.

Educational and informational use only. Not investment advice.
