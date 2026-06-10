"""Google Maps Platform integration: Routes API + Elevation API.

Everything degrades gracefully: any network/key failure raises
GoogleUnavailable and callers fall back to the synthetic engines, so the
app never hard-depends on Google being reachable.
"""

from __future__ import annotations

import json
from typing import Callable, List, Optional, Tuple

import httpx

from . import geo
from .google_config import CACHE_DIR, google_api_key
from .models import Maneuver

LonLat = Tuple[float, float]

ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
ELEVATION_URL = "https://maps.googleapis.com/maps/api/elevation/json"

FIELD_MASK = ",".join([
    "routes.duration",
    "routes.distanceMeters",
    "routes.description",
    "routes.polyline.encodedPolyline",
    "routes.legs.steps.navigationInstruction",
    "routes.legs.steps.distanceMeters",
    "routes.legs.steps.staticDuration",
    "routes.legs.steps.startLocation",
])


class GoogleUnavailable(RuntimeError):
    """Raised when live Google data cannot be fetched; callers must fall back."""


# ---------------------------------------------------------------------------
# Encoded polyline (precision 5) decoder — no third-party dependency.
# ---------------------------------------------------------------------------

def decode_polyline(encoded: str) -> List[List[float]]:
    """Decode a Google encoded polyline into [[lon, lat], ...]."""
    points: List[List[float]] = []
    index = lat = lon = 0
    while index < len(encoded):
        for is_lon in (False, True):
            shift = result = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if is_lon:
                lon += delta
            else:
                lat += delta
        points.append([lon / 1e5, lat / 1e5])
    return points


# ---------------------------------------------------------------------------
# Routes API
# ---------------------------------------------------------------------------

_MANEUVER_MAP = {
    "TURN_RIGHT": "turn_right",
    "TURN_LEFT": "turn_left",
    "TURN_SLIGHT_RIGHT": "slight_right",
    "TURN_SLIGHT_LEFT": "slight_left",
    "TURN_SHARP_RIGHT": "turn_right",
    "TURN_SHARP_LEFT": "turn_left",
    "UTURN_RIGHT": "uturn",
    "UTURN_LEFT": "uturn",
    "RAMP_RIGHT": "merge",
    "RAMP_LEFT": "merge",
    "MERGE": "merge",
    "ROUNDABOUT_RIGHT": "turn_right",
    "ROUNDABOUT_LEFT": "turn_left",
    "STRAIGHT": "continue",
    "NAME_CHANGE": "continue",
    "DEPART": "depart",
}


def _parse_duration_s(value: str | None) -> float:
    if not value:
        return 0.0
    return float(str(value).rstrip("s") or 0)


def _road_from_instruction(text: str) -> str:
    """Best-effort road name out of 'Turn right onto W Sunset Blvd'."""
    for marker in (" onto ", " on ", " toward "):
        if marker in text:
            return text.split(marker, 1)[1].split(",")[0].strip()
    return text.strip()


def steps_to_maneuvers(steps: List[dict], dest_name: str,
                       final_point: List[float]) -> List[Maneuver]:
    """Map Google steps to our Maneuver model.

    Google semantics: a step's navigationInstruction is performed AT the
    step's start; our distanceMeters is the distance travelled BEFORE the
    maneuver, i.e. the PREVIOUS step's length.
    """
    maneuvers: List[Maneuver] = []
    prev_dist = 0.0
    prev_time = 0.0
    for i, step in enumerate(steps):
        nav = step.get("navigationInstruction") or {}
        raw = nav.get("maneuver", "STRAIGHT")
        text = (nav.get("instructions") or "Continue").replace("\n", " — ").strip()
        mtype = _MANEUVER_MAP.get(raw, "continue")
        loc = step.get("startLocation", {}).get("latLng", {})
        coord = [loc.get("longitude", final_point[0]), loc.get("latitude", final_point[1])]
        if i == 0:
            mtype = "depart"
        maneuvers.append(Maneuver(
            id=f"g{i}", type=mtype,  # type: ignore[arg-type]
            instruction=text, roadName=_road_from_instruction(text),
            distanceMeters=round(prev_dist, 0), expectedTimeSeconds=round(prev_time, 0),
            coordinate=coord))
        prev_dist = float(step.get("distanceMeters", 0) or 0)
        prev_time = _parse_duration_s(step.get("staticDuration"))
    maneuvers.append(Maneuver(
        id=f"g{len(steps)}", type="arrive",
        instruction=f"Arrive at {dest_name} — simulated lower-risk zone",
        roadName=dest_name, distanceMeters=round(prev_dist, 0),
        expectedTimeSeconds=round(prev_time, 0), coordinate=list(final_point)))
    return maneuvers


def parse_routes_response(payload: dict, dest_name: str) -> List[dict]:
    """Normalize computeRoutes JSON into route dicts the engine can score."""
    out: List[dict] = []
    for route in payload.get("routes", []):
        encoded = (route.get("polyline") or {}).get("encodedPolyline")
        if not encoded:
            continue
        polyline = decode_polyline(encoded)
        steps: List[dict] = []
        for leg in route.get("legs", []):
            steps.extend(leg.get("steps", []))
        out.append({
            "polyline": polyline,
            "maneuvers": steps_to_maneuvers(steps, dest_name, polyline[-1]),
            "distanceMeters": float(route.get("distanceMeters", 0) or geo.polyline_length_m(
                [tuple(p) for p in polyline])),
            "durationMinutes": _parse_duration_s(route.get("duration")) / 60.0,
            "description": route.get("description") or "",
        })
    return out


def compute_routes(origin: LonLat, destination: LonLat, dest_name: str,
                   timeout_s: float = 7.0) -> List[dict]:
    """Live driving directions with alternatives from the Google Routes API."""
    key = google_api_key()
    if not key:
        raise GoogleUnavailable("GOOGLE_MAPS_API_KEY not set")
    body = {
        "origin": {"location": {"latLng": {"latitude": origin[1], "longitude": origin[0]}}},
        "destination": {"location": {"latLng": {"latitude": destination[1],
                                                "longitude": destination[0]}}},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_UNAWARE",
        "computeAlternativeRoutes": True,
        "polylineQuality": "HIGH_QUALITY",
        "units": "IMPERIAL",
        "languageCode": "en-US",
    }
    try:
        resp = httpx.post(
            ROUTES_URL, json=body, timeout=timeout_s,
            headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELD_MASK})
        resp.raise_for_status()
        routes = parse_routes_response(resp.json(), dest_name)
    except (httpx.HTTPError, json.JSONDecodeError, KeyError, ValueError) as exc:
        raise GoogleUnavailable(f"Routes API failed: {exc}") from exc
    if not routes:
        raise GoogleUnavailable("Routes API returned no routes")
    return routes


# ---------------------------------------------------------------------------
# Elevation API — one cached grid over the scenario area feeds the fire
# model's slope factor and the frontend's height lookups with REAL terrain.
# ---------------------------------------------------------------------------

GRID_CACHE = CACHE_DIR / "google_elevation_grid.json"
GRID_SPACING_M = 150.0


class ElevationGrid:
    def __init__(self, west: float, south: float, east: float, north: float,
                 cols: int, rows: int, heights: List[float], source: str):
        self.west, self.south, self.east, self.north = west, south, east, north
        self.cols, self.rows = cols, rows
        self.heights = heights  # row-major from south-west corner
        self.source = source

    def height_at(self, lon: float, lat: float) -> float:
        """Bilinear interpolation; clamps to grid edges."""
        fx = (lon - self.west) / (self.east - self.west) * (self.cols - 1)
        fy = (lat - self.south) / (self.north - self.south) * (self.rows - 1)
        fx = max(0.0, min(self.cols - 1.001, fx))
        fy = max(0.0, min(self.rows - 1.001, fy))
        x0, y0 = int(fx), int(fy)
        dx, dy = fx - x0, fy - y0
        h = self.heights

        def at(x: int, y: int) -> float:
            return h[y * self.cols + x]

        return (at(x0, y0) * (1 - dx) * (1 - dy) + at(x0 + 1, y0) * dx * (1 - dy)
                + at(x0, y0 + 1) * (1 - dx) * dy + at(x0 + 1, y0 + 1) * dx * dy)

    def to_payload(self) -> dict:
        return {"west": self.west, "south": self.south, "east": self.east,
                "north": self.north, "cols": self.cols, "rows": self.rows,
                "heights": [round(v, 1) for v in self.heights], "source": self.source}

    @staticmethod
    def from_payload(p: dict) -> "ElevationGrid":
        return ElevationGrid(p["west"], p["south"], p["east"], p["north"],
                             p["cols"], p["rows"], p["heights"], p.get("source", "cache"))


def _fetch_grid_from_google(bounds: List[float], timeout_s: float = 10.0) -> ElevationGrid:
    west, south, east, north = bounds
    cols = max(2, int((east - west) * geo.m_per_deg_lon() / GRID_SPACING_M) + 1)
    rows = max(2, int((north - south) * geo.M_PER_DEG_LAT / GRID_SPACING_M) + 1)
    locations: List[Tuple[float, float]] = []
    for r in range(rows):
        lat = south + (north - south) * r / (rows - 1)
        for c in range(cols):
            lon = west + (east - west) * c / (cols - 1)
            locations.append((lat, lon))
    heights: List[float] = []
    key = google_api_key()
    try:
        with httpx.Client(timeout=timeout_s) as client:
            for i in range(0, len(locations), 256):
                chunk = locations[i:i + 256]
                locs = "|".join(f"{la:.6f},{lo:.6f}" for la, lo in chunk)
                resp = client.get(ELEVATION_URL, params={"locations": locs, "key": key})
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") != "OK":
                    raise GoogleUnavailable(f"Elevation API status {data.get('status')}")
                heights.extend(float(r["elevation"]) for r in data["results"])
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
        raise GoogleUnavailable(f"Elevation API failed: {exc}") from exc
    if len(heights) != rows * cols:
        raise GoogleUnavailable("Elevation API returned incomplete grid")
    return ElevationGrid(west, south, east, north, cols, rows, heights, "google_elevation_api")


_grid: Optional[ElevationGrid] = None
_grid_failed = False


def elevation_grid(bounds: List[float]) -> Optional[ElevationGrid]:
    """Cached real-terrain grid: memory -> disk -> Google -> None (fallback)."""
    global _grid, _grid_failed
    if _grid is not None:
        return _grid
    if _grid_failed:
        return None
    if GRID_CACHE.exists():
        try:
            _grid = ElevationGrid.from_payload(json.loads(GRID_CACHE.read_text()))
            return _grid
        except (json.JSONDecodeError, KeyError):
            pass
    if not google_api_key():
        _grid_failed = True
        return None
    try:
        _grid = _fetch_grid_from_google(bounds)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        GRID_CACHE.write_text(json.dumps(_grid.to_payload()))
        return _grid
    except GoogleUnavailable:
        _grid_failed = True
        return None


def height_function(bounds: List[float]) -> Callable[[float, float], float]:
    """Real terrain when available, analytic twin otherwise."""
    grid = elevation_grid(bounds)
    if grid is None:
        return geo.terrain_height_m
    return grid.height_at


def slope_function(bounds: List[float]) -> Callable[[float, float, float, float], float]:
    height = height_function(bounds)

    def slope(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
        d = geo.haversine_m(lon1, lat1, lon2, lat2)
        if d < 1.0:
            return 0.0
        return (height(lon2, lat2) - height(lon1, lat1)) / d

    return slope


def reset_grid_cache_for_tests() -> None:
    global _grid, _grid_failed
    _grid = None
    _grid_failed = False


def grid_status(bounds: List[float]) -> dict:
    grid = elevation_grid(bounds)
    if grid is None:
        return {"mode": "analytic_twin",
                "note": "Synthetic heightfield (set GOOGLE_MAPS_API_KEY for real Google elevation)"}
    return {"mode": "google_elevation", "cols": grid.cols, "rows": grid.rows,
            "source": grid.source}
