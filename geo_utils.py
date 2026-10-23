"""Geocoding helpers (Nominatim) with rate limiting, timeouts and safe failure."""
from __future__ import annotations

import logging
import os
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

USER_AGENT = os.environ.get("NOMINATIM_USER_AGENT", "mumbai-fare-estimator/2.0 (student project)")
# Search is restricted to the greater Mumbai region: (lat, lon) corners.
MUMBAI_VIEWBOX = [(19.45, 72.70), (18.85, 73.20)]

_geocode = None
_reverse = None


def _init() -> None:
    global _geocode, _reverse
    if _geocode is not None:
        return
    from geopy.extra.rate_limiter import RateLimiter
    from geopy.geocoders import Nominatim

    geolocator = Nominatim(user_agent=USER_AGENT, timeout=10)
    # Nominatim's usage policy allows at most 1 request/second.
    _geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.1, max_retries=2,
                           error_wait_seconds=2.0, swallow_exceptions=True)
    _reverse = RateLimiter(geolocator.reverse, min_delay_seconds=1.1, max_retries=2,
                           error_wait_seconds=2.0, swallow_exceptions=True)


def search_location(query: str) -> Optional[Tuple[float, float, str]]:
    """Return (lat, lon, address) for a place inside the Mumbai region, or None."""
    query = (query or "").strip()[:200]
    if not query:
        return None
    try:
        _init()
        loc = _geocode(query, viewbox=MUMBAI_VIEWBOX, bounded=True, country_codes="in",
                       exactly_one=True, language="en")
    except Exception as exc:  # network / library errors must never crash the UI
        logger.warning("Geocoding failed for %r: %s", query, exc)
        return None
    if loc is None:
        return None
    return float(loc.latitude), float(loc.longitude), str(loc.address)


def reverse_geocode(lat: float, lon: float) -> str:
    """Address for a coordinate; falls back to 'lat, lon' text if the service is down."""
    fallback = f"{lat:.5f}, {lon:.5f}"
    try:
        _init()
        loc = _reverse((lat, lon), language="en", exactly_one=True)
    except Exception as exc:
        logger.warning("Reverse geocoding failed for %s,%s: %s", lat, lon, exc)
        return fallback
    return str(loc.address) if loc is not None else fallback
