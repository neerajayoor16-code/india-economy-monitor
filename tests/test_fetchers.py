"""Fetcher tests on saved real responses (tests/fixtures, downloaded 22 Nov 2026).

Each parser has:
  - a test that it reads the real file and gets the value published by the source;
  - tests that broken or changed input makes it FAIL (FetchError), never guess.
No network is used.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fetchers import FetchError, gst, mospi, oecd, pib, rbi  # noqa: E402

F = ROOT / "tests" / "fixtures"


def text(name):
    return (F / name).read_text("utf8", errors="replace")


# --------------------------------------------------------------------- MoSPI
def test_cpi_reads_combined_general_inflation():
    r = mospi.parse_cpi(json.loads(text("mospi_cpi_2026_10.json")))
    assert (r.value, r.period_label, r.period_end) == (6.09, "Oct 2026", "2026-10-31")
    assert r.details["inflation_by_sector"] == {"Rural": 6.63, "Urban": 5.41, "Combined": 6.09}


def test_cpi_fails_without_headline_row():
    payload = json.loads(text("mospi_cpi_2026_10.json"))
    payload["data"] = [r for r in payload["data"] if r["sector"] != "Combined"]
    with pytest.raises(FetchError, match="expected 1"):
        mospi.parse_cpi(payload)


def test_wpi_yoy_from_index_levels():
    r = mospi.compute_wpi(113.3, 100.9, 2026, 10)
    assert r.value == 12.29  # 113.3 / 100.9 - 1


def test_wpi_rejects_bad_base():
    with pytest.raises(FetchError):
        mospi.compute_wpi(113.3, 0, 2026, 10)


def test_iip_latest_month_and_previous():
    r = mospi.parse_iip(json.loads(text("mospi_iip_2026.json")))
    assert (r.value, r.period_label, r.previous, r.previous_label) == (6.7, "Sep 2026", 7.8, "Aug 2026")


def test_iip_fails_on_empty():
    with pytest.raises(FetchError):
        mospi.parse_iip([])


def test_gdp_growth_from_constant_prices():
    r = mospi.parse_gdp(json.loads(text("mospi_nas_gdp_quarterly.json")))
    assert (r.value, r.period_label, r.period_end) == (7.8, "Q1 FY27", "2026-06-30")


def test_unemployment_selects_headline_rate():
    rows = [
        {"state": "All India", "AgeGroup": "15 years and above", "gender": "person", "sector": "rural + urban", "year": "2026", "month": "October", "value": "4.9"},
        {"state": "All India", "AgeGroup": "15 years and above", "gender": "person", "sector": "rural + urban", "year": "2026", "month": "September", "value": "5"},
        {"state": "All India", "AgeGroup": "15-29 years", "gender": "person", "sector": "rural + urban", "year": "2026", "month": "October", "value": "13.0"},
    ]
    r = mospi.parse_unemployment(rows)
    assert (r.value, r.period_label, r.previous) == (4.9, "Oct 2026", 5.0)


def test_unemployment_fails_without_headline_rows():
    with pytest.raises(FetchError):
        mospi.parse_unemployment([{"state": "All India", "AgeGroup": "15-29 years", "gender": "male", "sector": "rural", "year": "2026", "month": "October", "value": "12.7"}])


# --------------------------------------------------------------------- OECD
def test_cli_level_and_direction():
    r = oecd.parse_cli(text("oecd_cli_ind.csv"))
    assert (r.value, r.period_label, r.previous) == (101.45, "Oct 2026", 101.39)
    assert r.details["rising"] is True


def test_cli_needs_two_months():
    head = text("oecd_cli_ind.csv").splitlines()
    with pytest.raises(FetchError):
        oecd.parse_cli("\n".join(head[:2]))


# --------------------------------------------------------------------- RBI
def test_rbi_home_rates_yield_nifty():
    h = rbi.parse_home(text("rbi_home.html"))
    assert h["repo_rate"].value == 5.50
    assert h["yield_spread"].details["ten_year_bond"] == "6.94% GS 2036"
    assert h["yield_spread"].value == 176  # (7.2629 - 5.50) * 100, rounded
    assert h["nifty"].value == 25514.30
    assert h["nifty"].period_end == "2026-11-19"


def test_rbi_home_fails_if_layout_changes():
    with pytest.raises(FetchError, match="Policy Repo Rate"):
        rbi.parse_home(text("rbi_home.html").replace("Policy Repo Rate", "Repo"))


def test_bank_credit_matches_rbi_stated_growth():
    r = rbi.parse_bank_credit(text("rbi_wss_extract.html"))
    assert (r.value, r.period_end) == (19.54, "2026-10-31")
    assert r.details["rbi_stated_growth"] == 19.5


def test_bank_credit_fails_when_numbers_disagree():
    broken = text("rbi_wss_extract.html").replace("3788844", "2788844")
    with pytest.raises(FetchError, match="does not match"):
        rbi.parse_bank_credit(broken)


def test_consumer_confidence_uses_rbi_formula():
    r = rbi.parse_consumer_confidence(text("rbi_uccs.html"))
    # 100 + (7.8 + 11.7 - 77.0 + 45.8 + 79.2) / 5 = 113.5  (CEIC reports 113.486)
    assert (r.value, r.period_label) == (113.5, "Sep 2026")
    assert (r.previous, r.previous_label) == (115.4, "Jul 2026")


def test_consumer_confidence_fails_if_a_table_is_missing():
    broken = text("rbi_uccs.html").replace("Perceptions and Expectations on Income", "Something else")
    with pytest.raises(FetchError, match="income"):
        rbi.parse_consumer_confidence(broken)


def test_industrial_outlook_expectations_index():
    r = rbi.parse_industrial_outlook(text("rbi_ios.html"))
    assert (r.value, r.previous, r.period_end) == (126.3, 111.1, "2026-12-31")


def test_rbi_feed_with_byte_order_mark():
    raw = b"\xef\xbb\xbf<?xml version='1.0'?><rss><channel><item><title>Weekly Statistical Supplement</title><link>https://x/y</link></item></channel></rss>"
    assert rbi.feed_items(raw) == [("Weekly Statistical Supplement", "https://x/y")]


# --------------------------------------------------------------------- PIB
def test_core_industries_headline():
    r = pib.parse_core_industries(text("pib_core_industries.html"))
    assert (r.value, r.period_label, r.previous) == (10.9, "Oct 2026", 8.2)


def test_core_industries_contraction_is_negative():
    page = "<p>The Index of Eight Core Industries (ICI) contracted by 1.5 per cent in March 2027 (Provisional).</p>"
    assert pib.parse_core_industries(page).value == -1.5


def test_rail_freight_growth_matches_stated():
    r = pib.parse_rail_freight(text("pib_rail_freight.html"))
    assert (r.value, r.period_label) == (8.32, "Oct 2026")
    assert r.details["stated_growth"] == 8.32  # the cross-check really ran


def test_rail_freight_fails_when_growth_disagrees():
    page = ("<p>Indian Railways loaded 145.07 million tonnes of freight during the month, compared to "
            "133.93 million tonnes in October 2025, registering a growth of 3.00 per cent.</p>")
    with pytest.raises(FetchError, match="does not match"):
        pib.parse_rail_freight(page)


# --------------------------------------------------------------------- GST
def test_gst_total_gross_revenue():
    r = gst.parse_gst((F / "gst_revenue_oct_2026.pdf").read_bytes())
    assert (r.value, r.display, r.period_label) == (22.9, "Rs. 2.31 Lakh Cr", "Oct 2026")
    assert (r.details["gross_crore"], r.details["gross_crore_year_ago"]) == (231290, 188125)


def test_gst_split_numbers_are_resolved_by_stated_growth():
    options = gst._indian_numbers("5 0,796 7 2,246")
    assert [50796.0, 72246.0] in options


def test_gst_rejects_non_pdf():
    with pytest.raises(Exception):
        gst.parse_gst(b"<html>not a pdf</html>")
