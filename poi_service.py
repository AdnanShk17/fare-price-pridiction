"""Places along a route (food, cafes, malls, attractions) from OpenStreetMap via Overpass.

OpenStreetMap has no ratings or crowd data, so places are ranked by how well documented
they are (Wikipedia/website/brand/opening hours) and how close they are to the route.
That is a proxy for "well-known", not a quality score. Opening hours may be missing.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import requests

logger = logging.getLogger(__name__)

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
REQUEST_TIMEOUT_S = 30
USER_AGENT = "mumbai-fare-estimator/2.0 (student project)"

MAX_PATH_POINTS = 60          # polyline points sent to Overpass
KM_PER_SEGMENT = 15.0         # long routes are queried in segments so results cover the whole way
MAX_SEGMENTS = 6
RESULTS_PER_SEGMENT = 60

CATEGORY_LABELS = {
    "food": "🍽️ Restaurants",
    "cafe": "☕ Cafés & quick bites",
    "mall": "🛍️ Malls & shopping",
    "attraction": "📸 Places to see",
}
CATEGORY_MARKERS = {  # folium (color, glyphicon)
    "food": ("darkpurple", "cutlery"),
    "cafe": ("cadetblue", "glass"),
    "mall": ("pink", "shopping-cart"),
    "attraction": ("darkblue", "camera"),
}
_BASE_SCORE = {"mall": 3.0, "attraction": 2.0, "food": 0.0, "cafe": 0.0}

# Overpass filters per category (name tag required so we never show unnamed places)
_FILTERS = {
    "food": ['nwr["amenity"~"^(restaurant|food_court)$"]["name"]'],
    "cafe": ['nwr["amenity"~"^(cafe|fast_food|ice_cream)$"]["name"]'],
    "mall": ['nwr["shop"="mall"]["name"]'],
    "attraction": ['nwr["tourism"~"^(attraction|viewpoint|museum|gallery|zoo|theme_park)$"]["name"]',
                   'nwr["historic"~"^(fort|castle|monument)$"]["name"]'],
}
_ATTRACTION_TOURISM = {"attraction", "viewpoint", "museum", "gallery", "zoo", "theme_park"}
_ATTRACTION_HISTORIC = {"fort", "castle", "monument"}

Point = Tuple[float, float]


class PoiError(Exception):
    """Raised when the places service cannot be reached or returns bad data."""


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def simplify_path(path: Sequence[Sequence[float]], max_points: int = MAX_PATH_POINTS) -> List[Point]:
    """Evenly thin a long polyline, always keeping the first and last point."""
    pts = [(float(p[0]), float(p[1])) for p in path]
    if len(pts) <= max_points:
        return pts
    idx = np.linspace(0, len(pts) - 1, max_points).round().astype(int)
    return [pts[i] for i in dict.fromkeys(idx.tolist())]


def _xy_km(lat, lon, lat0):
    """Local equirectangular projection (km) - accurate enough for a city-scale route."""
    return (np.asarray(lon) * 111.320 * math.cos(math.radians(lat0)),
            np.asarray(lat) * 110.574)


def path_cumulative_km(path: Sequence[Sequence[float]]) -> np.ndarray:
    arr = np.asarray(path, dtype=float)
    x, y = _xy_km(arr[:, 0], arr[:, 1], float(arr[:, 0].mean()))
    seg = np.hypot(np.diff(x), np.diff(y))
    return np.concatenate([[0.0], np.cumsum(seg)])


def nearest_on_path(path_arr: np.ndarray, lat: float, lon: float) -> Tuple[float, int]:
    """(distance in km to the closest path vertex, its index)."""
    lat0 = float(path_arr[:, 0].mean())
    px, py = _xy_km(path_arr[:, 0], path_arr[:, 1], lat0)
    qx, qy = _xy_km(lat, lon, lat0)
    d = np.hypot(px - qx, py - qy)
    i = int(np.argmin(d))
    return float(d[i]), i


def split_segments(points: Sequence[Point], km_per_segment: float = KM_PER_SEGMENT,
                   max_segments: int = MAX_SEGMENTS) -> List[List[Point]]:
    """Cut a polyline into <= max_segments pieces of roughly km_per_segment each."""
    pts = list(points)
    if len(pts) < 2:
        return [pts]
    total = float(path_cumulative_km(pts)[-1])
    n = int(min(max_segments, max(1, math.ceil(total / km_per_segment))))
    if n == 1:
        return [pts]
    size = math.ceil((len(pts) - 1) / n)
    segments = []
    for start in range(0, len(pts) - 1, size):
        seg = pts[start:start + size + 1]  # +1 so neighbouring segments share a point
        if len(seg) >= 2:
            segments.append(seg)
    return segments


# ---------------------------------------------------------------------------
# Overpass query / parsing
# ---------------------------------------------------------------------------
def build_query(segments: Sequence[Sequence[Point]], radius_m: int, categories: Sequence[str]) -> str:
    chosen = [c for c in categories if c in _FILTERS]
    if not chosen:
        raise ValueError("No valid categories selected")
    blocks = ["[out:json][timeout:25];"]
    for i, seg in enumerate(segments):
        coords = ",".join(f"{lat:.5f},{lon:.5f}" for lat, lon in seg)
        around = f"(around:{int(radius_m)},{coords})"
        stmts = "\n  ".join(f"{flt}{around};" for c in chosen for flt in _FILTERS[c])
        blocks.append(f"(\n  {stmts}\n)->.s{i};\n.s{i} out center {RESULTS_PER_SEGMENT};")
    return "\n".join(blocks)


def categorize(tags: Dict[str, str]) -> Optional[str]:
    if tags.get("shop") == "mall":
        return "mall"
    amenity = tags.get("amenity")
    if amenity in ("restaurant", "food_court"):
        return "food"
    if amenity in ("cafe", "fast_food", "ice_cream"):
        return "cafe"
    if tags.get("tourism") in _ATTRACTION_TOURISM or tags.get("historic") in _ATTRACTION_HISTORIC:
        return "attraction"
    return None


def parse_elements(data: dict) -> List[dict]:
    """Normalise Overpass elements into plain dicts (deduplicated)."""
    seen, places = set(), []
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        name = (tags.get("name:en") or tags.get("name") or "").strip()
        lat = el.get("lat", (el.get("center") or {}).get("lat"))
        lon = el.get("lon", (el.get("center") or {}).get("lon"))
        category = categorize(tags)
        if not name or lat is None or lon is None or category is None:
            continue
        key = (name.lower(), round(float(lat), 3), round(float(lon), 3))
        if key in seen:
            continue
        seen.add(key)
        places.append({"name": name, "lat": float(lat), "lon": float(lon),
                       "category": category, "tags": tags})
    return places


def fetch_pois(path: Sequence[Sequence[float]], radius_m: int = 500,
               categories: Sequence[str] = tuple(CATEGORY_LABELS),
               session: Optional[requests.Session] = None) -> List[dict]:
    """Query Overpass for named places near the route. Raises PoiError on failure."""
    simplified = simplify_path(path)
    if len(simplified) < 2:
        raise PoiError("Route is too short to search along")
    query = build_query(split_segments(simplified), radius_m, categories)
    poster = session.post if session else requests.post
    last_error: Optional[Exception] = None
    for url in OVERPASS_URLS:  # try the main server, then a mirror
        try:
            resp = poster(url, data={"data": query}, timeout=REQUEST_TIMEOUT_S,
                          headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            return parse_elements(resp.json())
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Overpass %s failed: %s", url, exc)
            last_error = exc
    raise PoiError(f"Places service unavailable: {last_error}")


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------
def notability(tags: Dict[str, str]) -> float:
    """Proxy for 'well known': well-documented places score higher. NOT a rating."""
    score = 0.0
    if tags.get("wikidata") or tags.get("wikipedia"):
        score += 3.0
    if tags.get("brand"):
        score += 1.0
    if tags.get("website") or tags.get("contact:website"):
        score += 1.0
    if tags.get("opening_hours"):
        score += 1.0
    if tags.get("phone") or tags.get("contact:phone"):
        score += 0.5
    if tags.get("cuisine"):
        score += 0.5
    return score


def _diversify(items: List[dict], limit: int, bins: int) -> List[dict]:
    """Pick the best items but spread them along the route instead of clustering."""
    buckets: List[List[dict]] = [[] for _ in range(bins)]
    for it in sorted(items, key=lambda x: -x["score"]):
        buckets[it["bin"]].append(it)
    picked: List[dict] = []
    while len(picked) < limit and any(buckets):
        for bucket in buckets:
            if bucket and len(picked) < limit:
                picked.append(bucket.pop(0))
    return sorted(picked, key=lambda x: x["route_fraction"])  # in travel order


def rank_pois(places: Sequence[dict], path: Sequence[Sequence[float]], duration_min: float,
              trip_dt: datetime, per_category: int = 5, bins: int = 5,
              max_off_route_m: Optional[float] = None) -> Dict[str, List[dict]]:
    """Attach route position / timing to each place and return the best few per category."""
    path_arr = np.asarray(path, dtype=float)
    if len(path_arr) < 2:
        return {}
    cum = path_cumulative_km(path_arr)
    total_km = float(cum[-1]) or 1.0

    by_cat: Dict[str, List[dict]] = {}
    for p in places:
        dist_km, idx = nearest_on_path(path_arr, p["lat"], p["lon"])
        off_m = dist_km * 1000
        if max_off_route_m is not None and off_m > max_off_route_m:
            continue
        fraction = float(cum[idx] / total_km)
        minutes = fraction * duration_min
        tags = p["tags"]
        item = {
            "id": f"{p['lat']:.5f}_{p['lon']:.5f}",
            "name": p["name"], "lat": p["lat"], "lon": p["lon"], "category": p["category"],
            "off_route_m": round(off_m),
            "route_fraction": round(fraction, 3),
            "minutes_into_trip": round(minutes),
            "pass_time": trip_dt + timedelta(minutes=minutes),
            "cuisine": (tags.get("cuisine") or "").replace(";", ", ").replace("_", " "),
            "opening_hours": (tags.get("opening_hours") or "")[:80],
            "website": tags.get("website") or tags.get("contact:website") or "",
            "bin": min(int(fraction * bins), bins - 1),
            "score": _BASE_SCORE[p["category"]] + notability(tags) - off_m / 250.0,
        }
        by_cat.setdefault(p["category"], []).append(item)
    return {cat: _diversify(items, per_category, bins) for cat, items in by_cat.items()}


def meal_context(hour: int) -> Tuple[str, str, List[str]]:
    """(emoji, headline, category display order) for the planned trip hour."""
    if 5 <= hour <= 10:
        return "🌅", "Breakfast & morning coffee", ["cafe", "food", "mall", "attraction"]
    if 11 <= hour <= 15:
        return "🍛", "Lunch time", ["food", "cafe", "mall", "attraction"]
    if 16 <= hour <= 18:
        return "🍵", "Evening snacks & chai", ["cafe", "food", "mall", "attraction"]
    if 19 <= hour <= 22:
        return "🍽️", "Dinner time", ["food", "cafe", "mall", "attraction"]
    return "🌙", "Late night - check opening hours before you stop", ["cafe", "food", "attraction", "mall"]
