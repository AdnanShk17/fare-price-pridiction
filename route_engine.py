import requests
from math import radians, sin, cos, sqrt, atan2
import json

# Haversine distance calculation fallback (in km)
def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c

def get_osrm_route(start_lat, start_lon, end_lat, end_lon, stops=None):
    """
    OSRM shortest driving route with optional intermediate stops.
    """

    if stops is None:
        stops = []

    # Build: Pickup -> Stops -> Drop
    # Remove empty stops before building the route
    valid_stops = [s for s in stops if s is not None]

    points = [(start_lat, start_lon)] + valid_stops + [(end_lat, end_lon)]

    coord_string = ";".join(
        [f"{lon},{lat}" for lat, lon in points]
    )

    url = (
        f"http://router.project-osrm.org/route/v1/driving/"
        f"{coord_string}?overview=full&geometries=geojson"
    )

    try:
        response = requests.get(url, timeout=8)

        if response.status_code == 200:
            data = response.json()

            if data.get("code") == "Ok":
                route = data["routes"][0]

                path_coordinates = [
                    [pt[1], pt[0]]
                    for pt in route["geometry"]["coordinates"]
                ]

                return {
                    "success": True,
                    "provider": "OSRM",
                    "algorithm": "Multi-Stop Routing",
                    "distance_km": round(route["distance"]/1000, 2),
                    "duration_min": round(route["duration"]/60, 1),
                    "path_coordinates": path_coordinates
                }

    except Exception as e:
        print(e)

    # Fallback
    total = 0

    for i in range(len(points)-1):
        total += haversine_distance(
            points[i][0], points[i][1],
            points[i+1][0], points[i+1][1]
        )

    duration = (total * 1.25 / 22) * 60

    return {
        "success": False,
        "provider": "Haversine",
        "algorithm": "Fallback",
        "distance_km": round(total * 1.25, 2),
        "duration_min": round(duration, 1),
        "path_coordinates": [[lat, lon] for lat, lon in points]
    }
def get_routing_algorithms_summary():
    """
    Returns comparative technical breakdown of shortest path algorithms
    for inclusion in academic reports and guide presentations.
    """
    return [
        {
            "algorithm": "Dijkstra's Algorithm",
            "type": "Graph Search / Single Source Shortest Path",
            "time_complexity": "O((V + E) log V)",
            "description": "Explores nodes equally in all directions based on path cost. Guarantees absolute shortest path but explores many unnecessary nodes on large road networks.",
            "status_in_app": "Conceptual Baseline"
        },
        {
            "algorithm": "A* (A-Star) Search",
            "type": "Heuristic Graph Search",
            "time_complexity": "O(E)",
            "description": "Extends Dijkstra by adding a spatial heuristic (e.g. Euclidean / Haversine distance to target). Focuses search directionally towards the destination, greatly reducing search space.",
            "status_in_app": "Conceptual Upgrade"
        },
        {
            "algorithm": "OSRM (Multi-Level Dijkstra / Contraction Hierarchies)",
            "type": "Preprocessed Hierarchical Routing Engine",
            "time_complexity": "O(log V) Query Time",
            "description": "Pre-calculates shortcut edges across major highway networks (CH/MLD). Queries complete in milliseconds over nationwide OSM road maps.",
            "status_in_app": "Deployed Production Engine"
        }
    ]
