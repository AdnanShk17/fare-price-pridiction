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

def get_osrm_route(start_lat, start_lon, end_lat, end_lon):
    """
    Calls OSRM Public Demo Server to calculate shortest driving route,
    distance in KM, duration in minutes, and geometry line coordinates.
    """
    # OSRM expects coordinates as longitude,latitude
    url = f"http://router.project-osrm.org/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}?overview=full&geometries=geojson"
    
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == "Ok" and len(data.get("routes", [])) > 0:
                route = data["routes"][0]
                distance_km = route["distance"] / 1000.0  # meters to km
                duration_min = route["duration"] / 60.0    # seconds to min
                
                # Geometry is GeoJSON format: coordinates are [lon, lat]
                raw_coords = route["geometry"]["coordinates"]
                path_coordinates = [[point[1], point[0]] for point in raw_coords] # convert to [lat, lon]
                
                return {
                    "success": True,
                    "provider": "OSRM (Open Source Routing Machine)",
                    "algorithm": "Multi-Level Dijkstra / Contraction Hierarchies",
                    "distance_km": round(distance_km, 2),
                    "duration_min": round(duration_min, 1),
                    "path_coordinates": path_coordinates
                }
    except Exception as e:
        print(f"OSRM API call failed or timed out: {e}")
        
    # Fallback to straight-line Haversine math
    dist_km = haversine_distance(start_lat, start_lon, end_lat, end_lon)
    # Estimate road multiplier ~1.25x for city streets, avg speed 22 km/h
    road_dist_km = dist_km * 1.25
    duration_min = (road_dist_km / 22.0) * 60.0
    
    # Generate simple line segment for path
    path_coordinates = [
        [start_lat, start_lon],
        [(start_lat + end_lat) / 2, (start_lon + end_lon) / 2],
        [end_lat, end_lon]
    ]
    
    return {
        "success": False,
        "provider": "Haversine Fallback Engine",
        "algorithm": "Direct Distance Estimation",
        "distance_km": round(road_dist_km, 2),
        "duration_min": round(duration_min, 1),
        "path_coordinates": path_coordinates
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
