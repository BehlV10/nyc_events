"""Which NYC borough a coordinate falls in, from the official borough boundaries.

Uses the water-inclusive boundaries (nyc_boroughs.json), so piers, boats and island venues
resolve to the borough that governs them, and anything outside the city (Hoboken, Jersey
City, Yonkers, Nassau) resolves to None. A lat/lng rectangle can't tell those apart.
"""

import json
import os
from functools import lru_cache

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nyc_boroughs.json")


@lru_cache(maxsize=1)
def _boroughs():
    with open(_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)["boroughs"]
    out = []
    for name, polys in raw.items():
        for poly in polys:
            ring = poly[0]
            xs = [p[0] for p in ring]
            ys = [p[1] for p in ring]
            out.append((name, (min(xs), min(ys), max(xs), max(ys)), poly))
    return out


def _in_ring(x, y, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


@lru_cache(maxsize=50000)
def borough_at(lat, lng):
    """'manhattan' | 'brooklyn' | 'queens' | 'bronx' | 'staten_island', or None outside NYC."""
    try:
        y, x = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    for name, (x0, y0, x1, y1), poly in _boroughs():
        if not (x0 <= x <= x1 and y0 <= y <= y1):
            continue
        if _in_ring(x, y, poly[0]) and not any(_in_ring(x, y, hole) for hole in poly[1:]):
            return name
    return None


def in_nyc(lat, lng):
    return borough_at(lat, lng) is not None
