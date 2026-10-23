"""OSRM routing client with a safe straight-line fallback.

Note: OSRM returns the FASTEST route by travel time (free-flow, no live
traffic), not the shortest-distance route. The public demo server is rate
limited and intended for light use; set OSRM_BASE_URL to your own instance
for anything heavier.
"""
from __future__ import annotations

import logging
import os
from typing import Iterable, List, Optional, Sequence, Tuple

import requests

from fare_logic import haversine_km

logger = logging.getLogger(__name__)

OSRM_BASE_URL = os.environ.get("OSRM_BASE_URL", "https://router.project-osrm.org").rstrip("/")
REQUEST_TIMEOUT_S = 8
MAX_WAYPOINTS = 5  # pickup + up to 3 stops + drop
FALLBACK_DETOUR_FACTOR = 1.3
FALLBACK_SPEED_KMH = 22.0
USER_AGENT = "mumbai-fare-estimator/2.0 (student project)"

Point = Tuple[float, float]  # (lat, lon)


class RouteError(Exception):
    """Raised when OSRM cannot provide a route."""


def _valid_point(pt) -> bool:
    try:
        lat, lon = float(pt[0]), float(pt[1])
    except (TypeError, ValueError, IndexError):
        return False
    return -90 <= lat <= 90 and -180 <= lon <= 180


def build_points(start: Point, end: Point, stops: Optional[Iterable[Optional[Point]]] = None) -> List[Point]:
    """Pickup -> stops -> drop, skipping empty (None) stops."""
    points = [tuple(map(float, start))]
    points += [tuple(map(float, s)) for s in (stops or []) if s is not None]
    points.append(tuple(map(float, end)))
    if len(points) > MAX_WAYPOINTS:
        raise ValueError(f"At most {MAX_WAYPOINTS - 2} intermediate stops are supported")
    if not all(_valid_point(p) for p in points):
        raise ValueError("Invalid coordinates")
    return points


def fetch_osrm_route(points: Sequence[Point], session: Optional[requests.Session] = None) -> dict:
    """Call OSRM; raise RouteError on any failure (so callers never cache failures)."""
    coords = ";".join(f"{lon},{lat}" for lat, lon in points)
    url = f"{OSRM_BASE_URL}/route/v1/driving/{coords}"
    params = {"overview": "full", "geometries": "geojson"}
    getter = session.get if session else requests.get
    try:
        resp = getter(url, params=params, timeout=REQUEST_TIMEOUT_S, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise RouteError(f"OSRM request failed: {exc}") from exc

    if data.get("code") != "Ok" or not data.get("routes"):
        raise RouteError(f"OSRM returned code {data.get('code')!r}")
    try:
        route = data["routes"][0]
        return {
            "success": True,
            "provider": "OSRM",
            "algorithm": "Fastest driving route (free-flow, no live traffic)",
            "warning": None,
            "distance_km": round(route["distance"] / 1000, 2),
            "duration_min": round(route["duration"] / 60, 1),
            "path_coordinates": [[lat, lon] for lon, lat in route["geometry"]["coordinates"]],
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise RouteError(f"Unexpected OSRM response: {exc}") from exc


def fallback_route(points: Sequence[Point], reason: str = "") -> dict:
    """Straight-line estimate x detour factor, clearly flagged as an approximation."""
    straight = sum(haversine_km(a[0], a[1], b[0], b[1]) for a, b in zip(points, points[1:]))
    road_km = straight * FALLBACK_DETOUR_FACTOR
    return {
        "success": False,
        "provider": "Straight-line estimate",
        "algorithm": f"Haversine x {FALLBACK_DETOUR_FACTOR} detour factor (fallback)",
        "warning": "Routing service unavailable - distance and time are rough straight-line estimates."
                   + (f" ({reason})" if reason else ""),
        "distance_km": round(road_km, 2),
        "duration_min": round(road_km / FALLBACK_SPEED_KMH * 60, 1),
        "path_coordinates": [[lat, lon] for lat, lon in points],
    }


def get_osrm_route(start_lat, start_lon, end_lat, end_lon, stops=None, session=None) -> dict:
    """Convenience wrapper: OSRM if reachable, otherwise the flagged fallback."""
    points = build_points((start_lat, start_lon), (end_lat, end_lon), stops)
    try:
        return fetch_osrm_route(points, session=session)
    except RouteError as exc:
        logger.warning("%s", exc)
        return fallback_route(points, str(exc))


def get_routing_algorithms_summary() -> list:
    """Short technical comparison used in the report tab."""
    return [
        {
            "algorithm": "Dijkstra's Algorithm",
            "type": "Graph search / single-source shortest path",
            "time_complexity": "O((V + E) log V) with a binary heap",
            "description": "Expands nodes in order of path cost and guarantees an optimal path, but explores "
                           "many irrelevant nodes on a large road network.",
            "status_in_app": "Conceptual baseline",
        },
        {
            "algorithm": "A* Search",
            "type": "Heuristic graph search",
            "time_complexity": "Worst case no better than Dijkstra; a good heuristic expands far fewer nodes",
            "description": "Adds an admissible heuristic (e.g. straight-line distance to the target) so the "
                           "search is pulled toward the destination.",
            "status_in_app": "Conceptual upgrade",
        },
        {
            "algorithm": "OSRM (Contraction Hierarchies / Multi-Level Dijkstra)",
            "type": "Preprocessed hierarchical routing engine",
            "time_complexity": "Heavy preprocessing; queries are typically milliseconds (no simple closed-form bound)",
            "description": "Precomputes shortcuts so queries touch very few nodes. Which of CH/MLD the public "
                           "server runs is outside this project's control.",
            "status_in_app": "Used through the public OSRM HTTP API (fastest route)",
        },
    ]
