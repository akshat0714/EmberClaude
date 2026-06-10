"""Geographic math + the synthetic Palisades terrain field.

Everything here is deterministic and dependency-free so the fire model,
route engine and tests behave identically on every run.

IMPORTANT — terrain:
v1 uses an ANALYTIC heightfield that approximates the Santa Monica
Mountains rising behind Pacific Palisades (coastal strip near sea level,
village mesa ~50-70 m, Palisades Highlands ridges 300-480 m, canyons
trending roughly N20E like Temescal / Santa Ynez canyons).

The *same formula, same constants* is implemented in
frontend/src/lib/terrain.ts and feeds Cesium's
CustomHeightmapTerrainProvider, so the 3D globe, the fire model's slope
factor and every placed entity agree on ground height without any
terrain service or API token. Swap in USGS 3DEP / Cesium World Terrain
later (docs/DATA_SOURCES_TO_ADD_LATER.md).
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

LonLat = Tuple[float, float]

M_PER_DEG_LAT = 111_320.0

# Reference point used for local meter coordinates (center of the scene).
REF_LON = -118.530
REF_LAT = 34.040


def m_per_deg_lon(lat: float = REF_LAT) -> float:
    return M_PER_DEG_LAT * math.cos(math.radians(lat))


def to_meters(lon: float, lat: float) -> Tuple[float, float]:
    """Local tangent-plane meters east/north of the scene reference."""
    return ((lon - REF_LON) * m_per_deg_lon(), (lat - REF_LAT) * M_PER_DEG_LAT)


def from_meters(x: float, y: float) -> LonLat:
    return (REF_LON + x / m_per_deg_lon(), REF_LAT + y / M_PER_DEG_LAT)


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def bearing_deg(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Initial bearing from point 1 to point 2, degrees clockwise from north."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def destination(lon: float, lat: float, bearing: float, dist_m: float) -> LonLat:
    """Flat-earth destination point — plenty accurate at neighborhood scale."""
    b = math.radians(bearing)
    dx = dist_m * math.sin(b)
    dy = dist_m * math.cos(b)
    return (lon + dx / m_per_deg_lon(lat), lat + dy / M_PER_DEG_LAT)


def angle_diff_deg(a: float, b: float) -> float:
    """Smallest absolute difference between two bearings (0..180)."""
    d = abs((a - b) % 360.0)
    return d if d <= 180.0 else 360.0 - d


def polyline_length_m(coords: Sequence[LonLat]) -> float:
    return sum(
        haversine_m(coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1])
        for i in range(len(coords) - 1)
    )


def point_along_polyline(coords: Sequence[LonLat], dist_m: float) -> Tuple[LonLat, float]:
    """Point at dist_m along the polyline plus the local heading there."""
    if dist_m <= 0:
        hdg = bearing_deg(*coords[0], *coords[1]) if len(coords) > 1 else 0.0
        return coords[0], hdg
    remaining = dist_m
    for i in range(len(coords) - 1):
        seg = haversine_m(coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1])
        if seg <= 1e-9:
            continue
        if remaining <= seg:
            f = remaining / seg
            lon = coords[i][0] + (coords[i + 1][0] - coords[i][0]) * f
            lat = coords[i][1] + (coords[i + 1][1] - coords[i][1]) * f
            return (lon, lat), bearing_deg(*coords[i], *coords[i + 1])
        remaining -= seg
    hdg = bearing_deg(*coords[-2], *coords[-1]) if len(coords) > 1 else 0.0
    return coords[-1], hdg


def resample_polyline(coords: Sequence[LonLat], step_m: float) -> List[LonLat]:
    total = polyline_length_m(coords)
    if total <= step_m:
        return [coords[0], coords[-1]]
    n = max(2, int(total / step_m) + 1)
    return [point_along_polyline(coords, total * i / (n - 1))[0] for i in range(n)]


def nearest_point_on_polyline(coords: Sequence[LonLat], lon: float, lat: float,
                              step_m: float = 25.0) -> Tuple[LonLat, float, float]:
    """(closest point, distance to it in m, progress along line in m). Sampled."""
    total = polyline_length_m(coords)
    n = max(2, int(total / step_m) + 1)
    best = (coords[0], float("inf"), 0.0)
    for i in range(n):
        prog = total * i / (n - 1)
        p, _ = point_along_polyline(coords, prog)
        d = haversine_m(p[0], p[1], lon, lat)
        if d < best[1]:
            best = (p, d, prog)
    return best


def point_in_polygon(lon: float, lat: float, polygon: Sequence[LonLat]) -> bool:
    """Ray-casting point-in-polygon test (polygon as [[lon,lat], ...])."""
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > lat) != (yj > lat):
            x_cross = (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi
            if lon < x_cross:
                inside = not inside
        j = i
    return inside


def polygon_area_sqkm(polygon: Sequence[LonLat]) -> float:
    """Shoelace area on the local tangent plane, in km^2."""
    pts = [to_meters(lon, lat) for lon, lat in polygon]
    s = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0 / 1e6


def hash_noise(ix: float, iy: float) -> float:
    """Deterministic pseudo-noise in [0,1) — classic sin-hash, no RNG state."""
    v = math.sin(ix * 127.1 + iy * 311.7) * 43758.5453123
    return v - math.floor(v)


def _smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


# ---------------------------------------------------------------------------
# Synthetic terrain (mirror of frontend/src/lib/terrain.ts — keep in sync!)
# ---------------------------------------------------------------------------

# Approximate Santa Monica Bay coastline as a line in lon/lat space.
COAST_REF_LON = -118.498
COAST_LAT_AT_REF = 34.008
COAST_SLOPE = -0.55  # coastline trends WNW: lat rises as lon decreases


def coast_lat(lon: float) -> float:
    return COAST_LAT_AT_REF + COAST_SLOPE * (lon - COAST_REF_LON)


def terrain_height_m(lon: float, lat: float) -> float:
    """Synthetic but geographically-plausible elevation, in meters."""
    d_coast = (lat - coast_lat(lon)) * M_PER_DEG_LAT  # meters inland of coastline
    if d_coast <= 0.0:
        return -30.0  # ocean floor placeholder

    x, y = to_meters(lon, lat)
    inland = _smoothstep(d_coast / 5500.0)

    # Canyons/ridges trend ~N20E (Temescal, Santa Ynez). 'c' is the
    # cross-canyon coordinate; layered sines give irregular ridgelines.
    a = math.radians(20.0)
    c = x * math.cos(a) - y * math.sin(a)
    along = x * math.sin(a) + y * math.cos(a)
    ridge = (
        0.55 * math.sin(c / 430.0)
        + 0.30 * math.sin(c / 187.0 + 1.7)
        + 0.15 * math.sin(c / 921.0 + 0.6)
        + 0.18 * math.sin(along / 640.0 + c / 510.0)
    )
    ridge_n = max(0.0, min(1.0, 0.5 + 0.5 * ridge / 1.18))

    h = inland * (90.0 + 380.0 * ridge_n * inland)

    # Flatten the village mesa around the "alphabet streets".
    mesa = math.exp(-(((lon + 118.522) / 0.011) ** 2) - (((lat - 34.041) / 0.0075) ** 2))
    h = h * (1.0 - 0.8 * mesa) + (50.0 + d_coast * 0.006) * (0.8 * mesa)

    # Keep a low coastal terrace so PCH hugs the shore below the bluffs.
    if d_coast < 260.0:
        h = min(h, 6.0 + d_coast * 0.05)
    return h


def slope_along(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Terrain gradient (rise/run) travelling from point 1 to point 2."""
    d = haversine_m(lon1, lat1, lon2, lat2)
    if d < 1.0:
        return 0.0
    return (terrain_height_m(lon2, lat2) - terrain_height_m(lon1, lat1)) / d
