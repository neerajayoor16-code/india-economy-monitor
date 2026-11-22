"""SIAM passenger vehicle sales.

Status (22 Nov 2026): SIAM's website certificate expired on 21 Nov 2026, so a safe
connection is not possible and the page format could not be checked. This fetcher
therefore always fails with a clear message. The card keeps its last value with a
stale warning. When siam.in has a valid certificate again, build parse_vehicles()
against a saved copy of the real page, then replace fetch_vehicles().
"""
from __future__ import annotations

import requests

from .common import FetchError, Reading, session

URL = "https://www.siam.in/"


def fetch_vehicles() -> Reading:
    try:
        session().get(URL, timeout=30)
    except requests.exceptions.SSLError as e:
        raise FetchError(f"SIAM: secure connection failed (site certificate problem): {e.__class__.__name__}") from e
    except requests.RequestException as e:
        raise FetchError(f"SIAM: site not reachable: {e}") from e
    raise FetchError("SIAM: site is reachable again, but the page parser is not built yet. "
                     "Save the press-release page as a test fixture and build parse_vehicles().")
