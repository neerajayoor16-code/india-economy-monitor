"""All fetchers in one place.

GROUPS maps a group name to a function that takes the current saved readings
(state: {indicator_id: reading dict}) and returns {indicator_id: Reading}.
One group can fill several indicators (the RBI home page gives three).

Outcomes a group can have:
  - returns readings            -> new data (the pipeline still checks it is not older)
  - raises NoNewRelease         -> nothing new published yet (normal)
  - raises FetchError           -> a real problem; the pipeline keeps old values and raises an alert
"""
from __future__ import annotations

import re
from typing import Callable

from . import gst, mospi, oecd, pib, rbi, siam
from .common import FetchError, NoNewRelease, Reading

State = dict[str, dict]


def _last_publication_id(state: State, indicator: str) -> int | None:
    url = (state.get(indicator) or {}).get("source_url") or ""
    m = re.search(r"PublicationsView\.aspx\?id=(\d+)", url, re.I)
    return int(m.group(1)) if m else None


GROUPS: dict[str, Callable[[State], dict[str, Reading]]] = {
    "mospi_cpi": lambda s: {"cpi": mospi.fetch_cpi()},
    "mospi_wpi": lambda s: {"wpi": mospi.fetch_wpi()},
    "mospi_iip": lambda s: {"iip": mospi.fetch_iip()},
    "mospi_unemployment": lambda s: {"unemployment": mospi.fetch_unemployment()},
    "mospi_gdp": lambda s: {"gdp": mospi.fetch_gdp()},
    "oecd_cli": lambda s: {"oecd_cli": oecd.fetch_cli()},
    "rbi_home": lambda s: rbi.fetch_home(),
    "rbi_bank_credit": lambda s: {"bank_credit": rbi.fetch_bank_credit()},
    "rbi_consumer_confidence": lambda s: {"consumer_confidence": rbi.fetch_consumer_confidence(
        _last_publication_id(s, "consumer_confidence"))},
    "rbi_industrial_outlook": lambda s: {"industrial_outlook": rbi.fetch_industrial_outlook(
        _last_publication_id(s, "industrial_outlook"))},
    "pib_core_industries": lambda s: {"core_industries": pib.fetch_core_industries()},
    "pib_rail_freight": lambda s: {"rail_freight": pib.fetch_rail_freight()},
    "gstn_gst": lambda s: {"gst": gst.fetch_gst()},
    "siam_vehicles": lambda s: {"vehicles": siam.fetch_vehicles()},
}

GROUP_INDICATORS = {
    "mospi_cpi": ["cpi"], "mospi_wpi": ["wpi"], "mospi_iip": ["iip"], "mospi_unemployment": ["unemployment"],
    "mospi_gdp": ["gdp"], "oecd_cli": ["oecd_cli"], "rbi_home": ["repo_rate", "yield_spread", "nifty"],
    "rbi_bank_credit": ["bank_credit"], "rbi_consumer_confidence": ["consumer_confidence"],
    "rbi_industrial_outlook": ["industrial_outlook"], "pib_core_industries": ["core_industries"],
    "pib_rail_freight": ["rail_freight"], "gstn_gst": ["gst"], "siam_vehicles": ["vehicles"],
}

# The 16 indicators, in the order the page shows them.
INDICATOR_IDS = [
    "cpi", "wpi", "unemployment", "bank_credit", "repo_rate",                      # past / lagging
    "core_industries", "iip", "rail_freight", "gst", "vehicles", "gdp",            # present / coincident
    "nifty", "yield_spread", "consumer_confidence", "industrial_outlook", "oecd_cli",  # future / leading
]

__all__ = ["GROUPS", "GROUP_INDICATORS", "INDICATOR_IDS", "FetchError", "NoNewRelease", "Reading", "State"]
