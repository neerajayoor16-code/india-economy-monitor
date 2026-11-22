"""Reserve Bank of India sources (all open web pages on www.rbi.org.in).

  - Home page "Current Rates" box: policy repo rate, government bond yields, Nifty 50.
  - Weekly Statistical Supplement extract (press release): bank credit growth.
  - Urban Consumer Confidence Survey: Future Expectations Index (computed with RBI's own formula).
  - Industrial Outlook Survey: Business Expectations Index.

New press releases and surveys are found through RBI's press-release feed.
RBI's data portal (DBIE) is NOT used: it encrypts its requests in the browser.
"""
from __future__ import annotations

import datetime as dt
import os
import re

from .common import MONTH_NUM, FetchError, NoNewRelease, Reading, html_lines, http_get, parse_xml, to_float

HOME = "https://www.rbi.org.in/home.aspx"
FEED = "https://www.rbi.org.in/pressreleases_rss.xml"
PUBLICATION = "https://www.rbi.org.in/Scripts/PublicationsView.aspx?id={id}"


def _date(text: str, what: str) -> dt.date:
    m = re.search(r"([A-Za-z]+)\.? (\d{1,2}), (\d{4})", text)
    if not m or m.group(1).lower()[:3] not in MONTH_NUM:
        raise FetchError(f"{what}: cannot read a date in {text!r}")
    return dt.date(int(m.group(3)), MONTH_NUM[m.group(1).lower()[:3]], int(m.group(2)))


def _value_after(lines: list[str], label: str, what: str) -> tuple[str, int]:
    """Home page layout: 'Label' / ':' / 'value'. Return the value text and its line index."""
    for i, ln in enumerate(lines):
        if ln.rstrip(" |") == label:
            for j in range(i + 1, min(i + 4, len(lines))):
                cand = lines[j].strip(" :|*#")
                if cand:
                    return cand, j
    raise FetchError(f"RBI home: {what} ({label!r}) not found")


# --------------------------------------------------------------------------- Home page: repo, 10-year yield, Nifty
def parse_home(page: str) -> dict[str, Reading]:
    lines = html_lines(page)
    repo_txt, _ = _value_after(lines, "Policy Repo Rate", "policy repo rate")
    repo = to_float(repo_txt.rstrip("%"), "repo rate")

    # Government securities: lines like "6.94% GS 2036" then ": 7.2629% # |"
    gs_date_line = next((ln for ln in lines if ln.startswith("# as on")), None)
    if not gs_date_line:
        raise FetchError("RBI home: date line for government securities ('# as on ...') not found")
    gs_date = _date(gs_date_line, "G-sec date")
    bonds = {}
    for i, ln in enumerate(lines):
        m = re.fullmatch(r"(\d+\.\d+)% GS (\d{4})", ln.rstrip(" |"))
        if m:
            ym = re.search(r"(\d+\.\d+)%", lines[i + 1] if i + 1 < len(lines) else "")
            if ln.find(":") < 0 and ym:
                bonds[int(m.group(2))] = (ln.rstrip(" |"), float(ym.group(1)))
            else:
                inline = re.search(r":\s*(\d+\.\d+)%", ln)
                if inline:
                    bonds[int(m.group(2))] = (ln, float(inline.group(1)))
    target = gs_date.year + 10
    if target not in bonds:
        raise FetchError(f"RBI home: no 10-year bond (maturing {target}) in {sorted(bonds)}")
    bond_name, y10 = bonds[target]
    spread = round((y10 - repo) * 100)

    # Capital market
    nifty_txt, j = _value_after(lines, "Nifty 50", "Nifty 50")
    nifty = to_float(nifty_txt, "Nifty 50")
    cm_date_line = next((ln for ln in lines[j:j + 6] if "as on" in ln), None)
    if not cm_date_line:
        raise FetchError("RBI home: date line for capital market not found")
    cm_date = _date(cm_date_line, "capital market date")
    sensex_txt, _ = _value_after(lines, "S&P BSE Sensex", "Sensex")

    # Repo has no "as on" date on the page; the reading date is the page date of the G-sec block.
    return {
        "repo_rate": Reading(
            indicator="repo_rate", value=repo, unit="%", display=f"{repo:.2f}%",
            period_label=gs_date.strftime("%b %d, %Y"), period_end=gs_date.isoformat(),
            source_name="RBI website (Current Rates)", source_url=HOME,
        ),
        "yield_spread": Reading(
            indicator="yield_spread", value=float(spread), unit="bps", display=f"{spread:+d} bps",
            period_label=gs_date.strftime("%b %d, %Y"), period_end=gs_date.isoformat(),
            source_name="RBI website (Government Securities Market)", source_url=HOME,
            details={"ten_year_bond": bond_name, "ten_year_yield": y10, "repo_rate": repo},
        ),
        "nifty": Reading(
            indicator="nifty", value=nifty, unit="points", display=f"{nifty:,.2f}",
            period_label=cm_date.strftime("%b %d, %Y"), period_end=cm_date.isoformat(),
            source_name="RBI website (Capital Market; index by NSE)", source_url=HOME,
            details={"sensex": to_float(sensex_txt, "Sensex")},
        ),
    }


def fetch_home() -> dict[str, Reading]:
    return parse_home(http_get(HOME).text)


# --------------------------------------------------------------------------- Feed discovery
def feed_items(raw: bytes) -> list[tuple[str, str]]:
    """Return (title, link) for each item in RBI's press-release feed."""
    root = parse_xml(raw, "RBI feed")
    out = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        if not title:
            title = re.sub(r"<[^>]+>", " ", it.findtext("description") or "").strip()
        out.append((re.sub(r"\s+", " ", title), (it.findtext("link") or "").strip()))
    return out


def find_in_feed(pattern: str) -> str | None:
    for title, link in feed_items(http_get(FEED).content):
        if re.search(pattern, title, re.I):
            return link
    return None


# --------------------------------------------------------------------------- Bank credit (Weekly Statistical Supplement extract)
def parse_bank_credit(page: str, url: str = "") -> Reading:
    lines = html_lines(page)
    date_line = next((ln for ln in lines if ln.startswith("Item | Outstanding as on")), None)
    if not date_line:
        raise FetchError("WSS: 'Outstanding as on' line for scheduled commercial banks not found")
    as_on = _date(date_line, "WSS bank credit date")
    row = next((ln for ln in lines if ln.startswith("7 Bank Credit |")), None)
    growth_row = next((ln for ln in lines if ln.startswith("7.1a Growth (Per cent)")), None)
    if not row or not growth_row:
        raise FetchError("WSS: '7 Bank Credit' or its growth row not found")
    cells = [c.strip() for c in row.split("|")[1:] if c.strip()]
    if len(cells) != 6:
        raise FetchError(f"WSS: bank credit row has {len(cells)} numbers, expected 6")
    outstanding, yoy_change = to_float(cells[0], "credit outstanding"), to_float(cells[5], "credit YoY change")
    computed = round(yoy_change / (outstanding - yoy_change) * 100, 2)
    stated = to_float([c for c in growth_row.split("|")[1:] if c.strip()][-1], "stated credit growth")
    if abs(computed - stated) > 0.1:
        raise FetchError(f"WSS: computed credit growth {computed} does not match RBI's stated {stated}")
    return Reading(
        indicator="bank_credit", value=computed, unit="%", display=f"{computed:.2f}% YoY",
        period_label=as_on.strftime("%b %d, %Y"), period_end=as_on.isoformat(),
        source_name="RBI Weekly Statistical Supplement", source_url=url or FEED,
        details={"outstanding_crore": outstanding, "yoy_change_crore": yoy_change, "rbi_stated_growth": stated},
    )


def fetch_bank_credit() -> Reading:
    link = find_in_feed(r"Weekly Statistical Supplement")
    if not link:
        raise NoNewRelease("WSS extract not in RBI's latest 10 press releases; will retry next run")
    return parse_bank_credit(http_get(link).text, link)


# --------------------------------------------------------------------------- Consumer confidence (Future Expectations Index)
_CCS_TITLE = re.compile(
    r"^Table \d+: Perceptions and Expectations on (the General Economic Situation|Employment|Price Level|Income|Spending) \|$")
_CCS_KEY = {"the General Economic Situation": "economy", "Employment": "employment",
            "Price Level": "prices", "Income": "income", "Spending": "spending"}


def _round_label(rnd: str | None) -> str | None:
    """'Jul-26' -> 'Jul 2026'"""
    if not rnd:
        return None
    mon, yy = rnd.split("-")
    return f"{mon} {2000 + int(yy)}"


def parse_consumer_confidence(page: str, url: str = "") -> Reading:
    """FEI = 100 + average of the one-year-ahead net responses for economy, employment,
    price level, income and spending (RBI's definition, stated on the same page).
    Each table's last column is the one-year-ahead net response."""
    lines = html_lines(page)
    if not any("Future Expectations Index" in ln for ln in lines):
        raise FetchError("CCS: page does not mention the Future Expectations Index")
    nets, rounds = {}, {}
    for i, ln in enumerate(lines):
        t = _CCS_TITLE.match(ln)
        if not t:
            continue
        key = _CCS_KEY[t.group(1)]
        rows = []
        for nxt in lines[i + 1:i + 20]:
            if nxt.startswith("Table "):
                break
            m = re.match(r"([A-Z][a-z]{2}-\d{2}) \| (.+)$", nxt)
            if m:
                rows.append((m.group(1), [c.strip() for c in m.group(2).split("|") if c.strip()]))
        if not rows:
            raise FetchError(f"CCS: no survey rows under the table for {key}")
        rounds[key] = rows[-1][0]
        nets[key] = to_float(rows[-1][1][-1], f"CCS {key} net response")
        prev = rows[-2] if len(rows) > 1 else None
        nets[key + "_prev"] = to_float(prev[1][-1], f"CCS {key} previous") if prev else None
        nets[key + "_prev_round"] = prev[0] if prev else None
    missing = [k for k in ("economy", "employment", "prices", "income", "spending") if k not in nets]
    if missing:
        raise FetchError(f"CCS: tables not found for {missing}")
    if len({rounds[k] for k in rounds}) != 1:
        raise FetchError(f"CCS: tables end on different survey rounds: {rounds}")
    keys = ("economy", "employment", "prices", "income", "spending")
    fei = round(100 + sum(nets[k] for k in keys) / 5, 1)
    prev_fei = None
    if all(nets.get(k + "_prev") is not None for k in keys):
        prev_fei = round(100 + sum(nets[k + "_prev"] for k in keys) / 5, 1)
    rnd = rounds["economy"]  # e.g. "Sep-26"
    mon, yy = rnd.split("-")
    year, month = 2000 + int(yy), MONTH_NUM[mon.lower()]
    from .common import month_end
    return Reading(
        indicator="consumer_confidence", value=fei, unit="index", display=f"{fei:.1f}",
        period_label=dt.date(year, month, 1).strftime("%b %Y"), period_end=month_end(year, month).isoformat(),
        source_name="RBI Urban Consumer Confidence Survey", source_url=url,
        previous=prev_fei, previous_label=_round_label(nets.get("economy_prev_round")),
        details={"net_responses_year_ahead": {k: nets[k] for k in keys}, "formula": "100 + average of 5 net responses"},
    )


# --------------------------------------------------------------------------- Industrial Outlook Survey (Business Expectations Index)
def parse_industrial_outlook(page: str, url: str = "") -> Reading:
    lines = html_lines(page)
    start = next((i for i, ln in enumerate(lines)
                  if ln.startswith("Quarter | Business Assessment Index (BAI) | Business Expectations Index (BEI)")), None)
    if start is None:
        raise FetchError("IOS: Business Sentiments table not found")
    rows = []
    for ln in lines[start + 1:start + 15]:
        m = re.match(r"(Q[1-4]):(\d{4})-(\d{2}) \| (.*)$", ln)
        if not m:
            break
        nums = [c.strip() for c in m.group(4).split("|")]
        nums = [c for c in nums if c != ""]
        rows.append((f"{m.group(1)} FY{m.group(3)}", m.group(1), int(m.group(2)), nums))
    with_bei = [r for r in rows if r[3]]
    if len(with_bei) < 2:
        raise FetchError("IOS: fewer than 2 quarters with a Business Expectations Index")
    label, q, fy_start, nums = with_bei[-1]
    bei = to_float(nums[-1], "BEI")
    p_label, _, _, p_nums = with_bei[-2]
    q_end = {"Q1": (0, 6, 30), "Q2": (0, 9, 30), "Q3": (0, 12, 31), "Q4": (1, 3, 31)}[q]
    end = dt.date(fy_start + q_end[0], q_end[1], q_end[2])
    return Reading(
        indicator="industrial_outlook", value=bei, unit="index", display=f"{bei:.1f}",
        period_label=f"{label} (expected)", period_end=end.isoformat(),
        source_name="RBI Industrial Outlook Survey", source_url=url,
        previous=to_float(p_nums[-1], "previous BEI"), previous_label=p_label,
    )


def _find_publication(title_pattern: str, last_known_id: int | None, probe: int = 40) -> tuple[str, str]:
    """Find a survey page: first via the press-release feed, then by checking the next publication ids."""
    link = find_in_feed(title_pattern)
    if link:
        page = http_get(link).text
        m = re.search(r"PublicationsView\.aspx\?id=(\d+)", page, re.I)
        if m:
            url = PUBLICATION.format(id=m.group(1))
            return http_get(url).text, url
    if os.environ.get("IEM_SKIP_PROBE"):
        raise NoNewRelease(f"no feed item for {title_pattern!r}; full search skipped on light runs")
    if last_known_id is None:
        raise FetchError(f"no feed item for {title_pattern!r} and no last known publication id")
    for pid in range(last_known_id + 1, last_known_id + 1 + probe):
        url = PUBLICATION.format(id=pid)
        try:
            page = http_get(url, retries=1).text
        except FetchError:
            continue
        head = " ".join(html_lines(page)[90:110])
        if re.search(title_pattern, head, re.I):
            return page, url
    raise NoNewRelease(f"no new publication matching {title_pattern!r} after id {last_known_id}")


def fetch_consumer_confidence(last_known_id: int | None = None) -> Reading:
    page, url = _find_publication(r"Consumer Confidence Survey", last_known_id)
    return parse_consumer_confidence(page, url)


def fetch_industrial_outlook(last_known_id: int | None = None) -> Reading:
    page, url = _find_publication(r"Industrial Outlook Survey", last_known_id)
    return parse_industrial_outlook(page, url)
