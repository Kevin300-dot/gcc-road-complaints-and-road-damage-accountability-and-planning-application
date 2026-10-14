"""
Area configuration: the Kandanchavadi boundary.

The boundary is the red line traced in Google My Maps and exported as KML
(data/kandanchavadi_boundary.kml). Everything that needs to know "is this
inside Kandanchavadi?" goes through this module.

Border rule: roads that run along the red line count as part of Kandanchavadi.
A point is therefore accepted if it is inside the polygon OR within
BORDER_TOLERANCE_M metres of the polygon edge (about half a road width plus
typical phone GPS error). In the 10 Oct 2026 field survey, 6 of the 48 points
were just outside the traced line, by 0.9 to 11.7 m, all on border roads.

To reuse the system for another ward: replace the KML file and change
AREA_NAME. Nothing else in this module is specific to Kandanchavadi.
"""
import math
import os
import re
import xml.etree.ElementTree as ET

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AREA_NAME = "Kandanchavadi"
BOUNDARY_KML_PATH = os.environ.get(
    "ORION_BOUNDARY_KML", os.path.join(BASE_DIR, "data", "kandanchavadi_boundary.kml")
)
BORDER_TOLERANCE_M = 15.0

_cache = {}


def _parse_kml_ring(path: str):
    """Returns the outer ring of the first polygon as a list of (lon, lat)."""
    tree = ET.parse(path)
    for el in tree.iter():
        tag = el.tag.split("}")[-1]
        if tag == "coordinates" and el.text and el.text.strip():
            ring = []
            for token in re.split(r"\s+", el.text.strip()):
                parts = token.split(",")
                if len(parts) >= 2:
                    ring.append((float(parts[0]), float(parts[1])))
            if len(ring) >= 4:
                if ring[0] != ring[-1]:
                    ring.append(ring[0])
                return ring
    raise ValueError(f"No polygon coordinates found in {path}")


def boundary_ring():
    """Boundary as a closed list of (lon, lat) points."""
    if "ring" not in _cache:
        _cache["ring"] = _parse_kml_ring(BOUNDARY_KML_PATH)
    return _cache["ring"]


def _origin():
    ring = boundary_ring()
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return (min(lons) + max(lons)) / 2, (min(lats) + max(lats)) / 2


def _to_xy(lon, lat):
    """Local equirectangular projection to metres around the boundary centre.
    Accurate to well under a metre over an area this small."""
    lon0, lat0 = _origin()
    return (
        (lon - lon0) * 111320.0 * math.cos(math.radians(lat0)),
        (lat - lat0) * 110574.0,
    )


def project(lat: float, lon: float):
    """Public helper: (x, y) in metres on the local projection used for all distance maths."""
    return _to_xy(lon, lat)


def _projected_ring():
    if "xy" not in _cache:
        _cache["xy"] = [_to_xy(lon, lat) for lon, lat in boundary_ring()]
    return _cache["xy"]


def _point_in_polygon(x, y, ring):
    inside = False
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        if (y1 > y) != (y2 > y):
            if x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                inside = not inside
    return inside


def _dist_to_segment(px, py, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def locate(lat: float, lon: float) -> dict:
    """Where a point sits relative to the boundary.

    Returns {"inside": bool, "distance_to_edge_m": float}. inside is the strict
    geometric test; use contains() for the border-road rule."""
    ring = _projected_ring()
    x, y = _to_xy(lon, lat)
    edge = min(_dist_to_segment(x, y, ring[i], ring[i + 1]) for i in range(len(ring) - 1))
    return {"inside": _point_in_polygon(x, y, ring), "distance_to_edge_m": round(edge, 1)}


def contains(lat: float, lon: float, tolerance_m: float = None) -> bool:
    """True if the point is in Kandanchavadi, counting border roads as inside."""
    if lat is None or lon is None:
        return False
    tol = BORDER_TOLERANCE_M if tolerance_m is None else tolerance_m
    info = locate(lat, lon)
    return info["inside"] or info["distance_to_edge_m"] <= tol


def bounds():
    """(south, west, north, east)."""
    ring = boundary_ring()
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return min(lats), min(lons), max(lats), max(lons)


def centroid():
    """(lat, lon) centre of the polygon (area-weighted)."""
    ring = _projected_ring()
    a = cx = cy = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    a *= 0.5
    cx /= 6 * a
    cy /= 6 * a
    lon0, lat0 = _origin()
    return lat0 + cy / 110574.0, lon0 + cx / (111320.0 * math.cos(math.radians(lat0)))


def area_km2() -> float:
    ring = _projected_ring()
    a = sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1))
    return abs(a) / 2 / 1e6


def to_geojson() -> dict:
    return {
        "type": "Feature",
        "properties": {"name": f"{AREA_NAME} boundary"},
        "geometry": {"type": "Polygon", "coordinates": [[list(p) for p in boundary_ring()]]},
    }


def info() -> dict:
    s, w, n, e = bounds()
    lat, lon = centroid()
    return {
        "name": AREA_NAME,
        "boundary": to_geojson(),
        "bounds": {"south": s, "west": w, "north": n, "east": e},
        "centre": {"latitude": lat, "longitude": lon},
        "area_km2": round(area_km2(), 4),
        "border_tolerance_m": BORDER_TOLERANCE_M,
    }
