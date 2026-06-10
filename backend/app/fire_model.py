"""Explainable cellular wildfire spread model (demo grade, deterministic).

The fire is an ARRAY of cells on an irregular ~115 m lattice, not a single
growing circle. Spread is computed with a fast-marching / Dijkstra sweep:
every burning cell offers ignition to its 16 compass neighbors and the
earliest offered ignition time wins.

Spread-rate formula for igniting a neighbor cell at bearing B
(documented so it can be swapped for Rothermel/FARSITE-class physics later):

    rate (m/min) = BASE_RATE
                   * windMult       # stronger wind -> faster everywhere
                   * alignMult(B)   # downwind >> crosswind >> upwind
                   * fuelMult       # chaparral burns faster than irrigated lawns
                   * slopeMult      # fire runs uphill, crawls downhill
                   * intensityMult  # scenario severity dial
                   * jitter         # deterministic per-cell noise -> ragged fronts

    delay   (min) = CELL_STEP_M / rate
    ignition(min) = parent.ignition + delay

Everything is deterministic: the only "randomness" is a hash of the cell's
lattice coordinates, so identical inputs always produce identical fire.
Confidence decays with each hop and with how far in the future the
ignition lies, which drives the dotted uncertainty envelope in the UI.

This is calibrated to *feel* like the explosive first hour of the
January 7, 2025 Palisades Fire (NNE Santa Ana wind driving fire from the
ridge above Piedra Morada Drive toward Palisades Highlands and the
village). It is a demo approximation, not a reconstruction.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from . import geo
from .models import (
    FireCell,
    FirePerimeter,
    RiskZone,
    SimulationRequest,
    SimulationResult,
    SmokeZone,
    UncertaintyEnvelope,
)

# --- Tunables (the knobs a real fire-behavior analyst would replace) -------
IGNITION_LONLAT = (-118.5421, 34.0708)  # near Piedra Morada Dr, approximate
# Wind-driven ember spotting jumps, approximating the documented explosive
# growth toward the Highlands/village side: (lon, lat, ignitionMinute, confidence)
SPOT_FIRES = [
    (-118.5330, 34.0570, 8.0, 0.85),   # ridge run along Temescal Ridge flank
    (-118.5165, 34.0435, 12.0, 0.75),  # ember spot in Rustic Canyon brush
]
BASE_RATE_M_PER_MIN = 9.0
CELL_STEP_M = 145.0
LATTICE_M = 115.0
CELL_RADIUS_M = 80.0
N_DIRECTIONS = 16
MIN_CONFIDENCE = 0.12
FULL_BURN_MINUTES = 22.0   # cells burn at full intensity this long...
DECAY_TAU_MINUTES = 30.0   # ...then decay toward burned-out
TIMELINE_MINUTES = list(range(0, 95, 5))

DEFAULTS = SimulationRequest()


@dataclass
class Cell:
    key: Tuple[int, int]
    lon: float
    lat: float
    ignition: float
    confidence: float
    fuel: float
    slope: float
    align: float
    rate: float
    radius: float


def _lattice_key(lon: float, lat: float) -> Tuple[int, int]:
    x, y = geo.to_meters(lon, lat)
    return (round(x / LATTICE_M), round(y / LATTICE_M))


def _wind_mult(wind_mph: float) -> float:
    return 0.55 + 1.25 * (wind_mph / 40.0)


def _align_mult(spread_bearing: float, wind_from_deg: float) -> float:
    """Downwind spread up to ~2.15x, crosswind ~0.55x, upwind floor 0.18x."""
    wind_to = (wind_from_deg + 180.0) % 360.0
    cos_t = math.cos(math.radians(geo.angle_diff_deg(spread_bearing, wind_to)))
    if cos_t >= 0.0:
        return 0.55 + 1.60 * (cos_t ** 1.8)
    return max(0.18, 0.55 + 0.45 * cos_t)


def _fuel_mult(fuel: float) -> float:
    return 0.30 + 1.10 * fuel


def _slope_mult(slope: float) -> float:
    return max(0.5, min(1.9, 1.0 + 2.4 * slope))


def _intensity_mult(intensity: float) -> float:
    return 0.55 + 0.65 * intensity


SlopeFn = Callable[[float, float, float, float], float]


def simulate_cells(params: SimulationRequest,
                   fuel_at: Callable[[float, float], float],
                   slope_fn: Optional[SlopeFn] = None) -> List[Cell]:
    """Fast-marching sweep: earliest ignition time wins at every lattice cell.

    slope_fn lets callers inject REAL terrain gradients (Google Elevation
    grid); the analytic twin heightfield is the default.
    """
    slope_of = slope_fn or geo.slope_along
    horizon = params.horizonMinutes
    cells: Dict[Tuple[int, int], Cell] = {}
    heap: List[Tuple[float, int, Tuple[int, int]]] = []
    counter = 0

    def add(lon: float, lat: float, ign: float, conf: float, fuel: float,
            slope: float, align: float, rate: float) -> None:
        nonlocal counter
        key = _lattice_key(lon, lat)
        existing = cells.get(key)
        if existing is not None and existing.ignition <= ign:
            return
        radius = CELL_RADIUS_M * (0.9 + 0.25 * geo.hash_noise(key[0] + 13.7, key[1] - 4.2))
        cells[key] = Cell(key, lon, lat, ign, conf, fuel, slope, align, rate, radius)
        counter += 1
        heapq.heappush(heap, (ign, counter, key))

    # Seed cluster: three cells around the documented ignition area.
    ilon, ilat = IGNITION_LONLAT
    for dx_b, dist in ((0.0, 0.0), (130.0, 90.0), (250.0, 110.0)):
        lon, lat = geo.destination(ilon, ilat, dx_b, dist)
        add(lon, lat, 0.0, 0.95, fuel_at(lon, lat), 0.0, 1.0, BASE_RATE_M_PER_MIN)
    # Scripted spotting ignitions (synthetic approximation of ember jumps).
    for slon, slat, sign, sconf in SPOT_FIRES:
        add(slon, slat, sign, sconf, fuel_at(slon, slat), 0.0, 1.0, BASE_RATE_M_PER_MIN)

    wind_mult = _wind_mult(params.windSpeedMph)
    int_mult = _intensity_mult(params.fireIntensity)

    while heap:
        ign, _, key = heapq.heappop(heap)
        cell = cells.get(key)
        if cell is None or cell.ignition < ign - 1e-9:
            continue  # stale heap entry
        if ign > horizon:
            break
        for k in range(N_DIRECTIONS):
            bearing = k * (360.0 / N_DIRECTIONS)
            nlon, nlat = geo.destination(cell.lon, cell.lat, bearing, CELL_STEP_M)
            nkey = _lattice_key(nlon, nlat)
            if nkey == key:
                continue
            fuel = fuel_at(nlon, nlat)
            if fuel < 0.08:
                continue  # ocean / bare ground does not carry fire
            slope = slope_of(cell.lon, cell.lat, nlon, nlat)
            align = _align_mult(bearing, params.windFromDeg)
            jitter = 0.85 + 0.30 * geo.hash_noise(nkey[0], nkey[1])
            rate = (BASE_RATE_M_PER_MIN * wind_mult * align * _fuel_mult(fuel)
                    * _slope_mult(slope) * int_mult * jitter)
            rate = max(rate, 0.5)
            delay = CELL_STEP_M / rate
            ign2 = ign + delay
            if ign2 > horizon:
                continue
            conf = cell.confidence * math.exp(-delay / 130.0)
            if conf < MIN_CONFIDENCE:
                continue
            add(nlon, nlat, ign2, conf, fuel, slope, align, rate)

    return sorted(cells.values(), key=lambda c: c.ignition)


def cell_intensity(cell: Cell, minute: float) -> float:
    """Ramp up ~2 min, burn ~22 min at full strength, then decay."""
    age = minute - cell.ignition
    if age < 0:
        return 0.0
    base = min(1.0, 0.45 + 0.40 * cell.fuel + 0.15 * min(1.0, cell.align / 2.15))
    ramp = min(1.0, 0.35 + age / 2.0)  # visible from the moment of ignition
    if age <= FULL_BURN_MINUTES:
        return base * ramp
    return base * math.exp(-(age - FULL_BURN_MINUTES) / DECAY_TAU_MINUTES)


def active_cells(cells: List[Cell], minute: float) -> List[Cell]:
    return [c for c in cells if c.ignition <= minute and cell_intensity(c, minute) >= 0.05]


def _to_fire_cell(cell: Cell, minute: float, source: str, now: float) -> FireCell:
    future = max(0.0, cell.ignition - now)
    return FireCell(
        id=f"cell-{cell.key[0]}-{cell.key[1]}",
        lat=round(cell.lat, 6),
        lon=round(cell.lon, 6),
        radiusMeters=round(cell.radius, 1),
        ignitionMinute=round(cell.ignition, 2),
        intensity=round(cell_intensity(cell, minute), 3),
        confidence=round(max(0.05, cell.confidence * math.exp(-future / 50.0)), 3),
        source=source,  # type: ignore[arg-type]
        fuelLoad=round(cell.fuel, 2),
        slopeFactor=round(cell.slope, 3),
        windAlignment=round(cell.align, 2),
        spreadRateMetersPerMinute=round(cell.rate, 1),
    )


# ---------------------------------------------------------------------------
# Perimeters: irregular polygon traced around the active cells via an
# angular sweep about the intensity-weighted centroid (star-shaped, ragged).
# ---------------------------------------------------------------------------

def _centroid(cells: List[Cell], minute: float) -> Tuple[float, float]:
    wx = wy = wsum = 0.0
    for c in cells:
        w = cell_intensity(c, minute) + 0.15
        x, y = geo.to_meters(c.lon, c.lat)
        wx += w * x
        wy += w * y
        wsum += w
    return (wx / wsum, wy / wsum) if wsum else (0.0, 0.0)


def perimeter_polygon(cells: List[Cell], minute: float, bins: int = 56) -> Optional[List[List[float]]]:
    act = active_cells(cells, minute)
    if not act:
        return None
    cx, cy = _centroid(act, minute)
    radii = [0.0] * bins
    for c in act:
        x, y = geo.to_meters(c.lon, c.lat)
        d = math.hypot(x - cx, y - cy)
        ang = math.atan2(y - cy, x - cx) % (2 * math.pi)
        b = int(ang / (2 * math.pi) * bins) % bins
        reach = d + c.radius * 1.15
        for bb in (b - 1, b, b + 1):
            i = bb % bins
            radii[i] = max(radii[i], reach * (1.0 if bb == b else 0.92))
    # Fill empty bins by circular interpolation, then smooth twice.
    filled = [r if r > 0 else None for r in radii]
    if any(v is None for v in filled):
        for i in range(bins):
            if filled[i] is None:
                prev_i, next_i = i, i
                while filled[prev_i % bins] is None:
                    prev_i -= 1
                while filled[next_i % bins] is None:
                    next_i += 1
                gap = next_i - prev_i
                f = (i - prev_i) / gap
                filled[i] = filled[prev_i % bins] * (1 - f) + filled[next_i % bins] * f  # type: ignore
    vals = [max(120.0, v) for v in filled]  # type: ignore[arg-type]
    for _ in range(2):
        vals = [0.25 * vals[i - 1] + 0.5 * vals[i] + 0.25 * vals[(i + 1) % bins]
                for i in range(bins)]
    poly = []
    for i in range(bins):
        ang = (i + 0.5) / bins * 2 * math.pi
        x = cx + vals[i] * math.cos(ang)
        y = cy + vals[i] * math.sin(ang)
        lon, lat = geo.from_meters(x, y)
        poly.append([round(lon, 6), round(lat, 6)])
    poly.append(poly[0])
    return poly


def scale_polygon(polygon: List[List[float]], outward_m: float) -> List[List[float]]:
    pts = [geo.to_meters(lon, lat) for lon, lat in polygon]
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    out = []
    for (x, y) in pts:
        d = math.hypot(x - cx, y - cy) or 1.0
        f = (d + outward_m) / d
        lon, lat = geo.from_meters(cx + (x - cx) * f, cy + (y - cy) * f)
        out.append([round(lon, 6), round(lat, 6)])
    return out


# ---------------------------------------------------------------------------
# Smoke plumes: each strong emitter pushes a downwind cone; the overall
# centroid pushes a large 3-level (heavy/moderate/light) plume. Polygons are
# served separately (no union needed) — overlap reads as denser smoke.
# ---------------------------------------------------------------------------

def _plume_polygon(lon: float, lat: float, wind_to: float, length: float,
                   start_w: float = 90.0, spread: float = 0.30) -> Tuple[List[List[float]], List[List[float]]]:
    steps = 8
    left, right = [], []
    for i in range(steps + 1):
        s = length * i / steps
        w = start_w + spread * s
        clon, clat = geo.destination(lon, lat, wind_to, s)
        wob = 1.0 + 0.18 * math.sin(s / 260.0 + lon * 90.0)  # ragged plume edge
        left.append(list(geo.destination(clon, clat, wind_to - 90, w * wob)))
        right.append(list(geo.destination(clon, clat, wind_to + 90, w * wob)))
    poly = left + right[::-1] + [left[0]]
    poly = [[round(p[0], 6), round(p[1], 6)] for p in poly]
    tip = geo.destination(lon, lat, wind_to, length)
    mid = geo.destination(lon, lat, wind_to, length / 2)
    center = [[lon, lat], [round(mid[0], 6), round(mid[1], 6)], [round(tip[0], 6), round(tip[1], 6)]]
    return poly, center


def smoke_zones_for_minute(cells: List[Cell], minute: float,
                           params: SimulationRequest) -> List[SmokeZone]:
    act = active_cells(cells, minute)
    if not act:
        return []
    wind_to = (params.windFromDeg + 180.0) % 360.0
    zones: List[SmokeZone] = []

    # Main column from the fire centroid, three nested density levels.
    cx, cy = _centroid(act, minute)
    clon, clat = geo.from_meters(cx, cy)
    main_len = min(5200.0, 1100.0 + 34.0 * params.windSpeedMph + 10.0 * minute)
    for frac, level, dens in ((0.32, "heavy", 0.85), (0.62, "moderate", 0.50), (1.0, "light", 0.25)):
        poly, center = _plume_polygon(clon, clat, wind_to, main_len * frac,
                                      start_w=120.0, spread=0.30)
        zones.append(SmokeZone(
            id=f"smoke-main-{level}-{int(minute)}", minute=int(minute),
            densityLevel=level, density=dens, polygon=poly, centerline=center,  # type: ignore[arg-type]
            plumeHeightMeters=round(220.0 + main_len * frac * 0.13, 0),
        ))

    # Flank plumes from the strongest spatially-distinct emitters.
    emitters: Dict[Tuple[int, int], Cell] = {}
    for c in sorted(act, key=lambda c: -cell_intensity(c, minute)):
        gkey = (round(c.lon * 200), round(c.lat * 200))  # ~500 m clusters
        if gkey not in emitters:
            emitters[gkey] = c
        if len(emitters) >= 7:
            break
    for i, c in enumerate(emitters.values()):
        inten = cell_intensity(c, minute)
        length = min(3400.0, (700.0 + 26.0 * params.windSpeedMph) * (0.5 + 0.8 * inten))
        poly, center = _plume_polygon(c.lon, c.lat, wind_to, length)
        dens = round(0.30 + 0.45 * inten, 2)
        level = "heavy" if dens > 0.6 else ("moderate" if dens > 0.38 else "light")
        zones.append(SmokeZone(
            id=f"smoke-flank-{i}-{int(minute)}", minute=int(minute),
            densityLevel=level, density=dens, polygon=poly, centerline=center,  # type: ignore[arg-type]
            plumeHeightMeters=round(160.0 + length * 0.11, 0),
        ))
    return zones


def smoke_density_at(zones: List[SmokeZone], lon: float, lat: float) -> float:
    """Max density of any plume polygon containing the point (0 if clear)."""
    best = 0.0
    for z in zones:
        if z.density > best and geo.point_in_polygon(lon, lat, z.polygon):
            best = z.density
    return best


# ---------------------------------------------------------------------------
# Fire arrival estimate — used by the route engine for buffer minutes.
# arrival(p) = min over cells of (ignition_i + dist_i / directional rate)
# ---------------------------------------------------------------------------

def fire_arrival_minute(cells: List[Cell], lon: float, lat: float,
                        params: SimulationRequest, cap: float = 240.0,
                        fuel_at: Optional[Callable[[float, float], float]] = None) -> float:
    wind_mult = _wind_mult(params.windSpeedMph)
    int_mult = _intensity_mult(params.fireIntensity)
    # Fire must burn the destination's fuel to arrive there: respecting the
    # target fuel keeps this estimate consistent with the lattice simulation
    # (e.g. irrigated suburbs buy real minutes, water buys forever).
    dest_fuel = fuel_at(lon, lat) if fuel_at is not None else 1.0
    if dest_fuel < 0.08:
        return cap
    best = cap
    for c in cells:
        d = geo.haversine_m(c.lon, c.lat, lon, lat)
        if d < c.radius:
            return min(best, c.ignition)
        bearing = geo.bearing_deg(c.lon, c.lat, lon, lat)
        fuel = min(max(0.3, c.fuel), dest_fuel) if fuel_at is not None else max(0.3, c.fuel)
        rate = (BASE_RATE_M_PER_MIN * wind_mult * _align_mult(bearing, params.windFromDeg)
                * _fuel_mult(fuel) * int_mult * 1.05)
        est = c.ignition + d / max(rate, 1.0)
        if est < best:
            best = est
    return best


# ---------------------------------------------------------------------------
# Full simulation bundle
# ---------------------------------------------------------------------------

def _risk_zones(cells: List[Cell], minute: int, params: SimulationRequest,
                smoke: List[SmokeZone]) -> List[RiskZone]:
    zones: List[RiskZone] = []
    now_poly = perimeter_polygon(cells, minute)
    if now_poly:
        zones.append(RiskZone(
            id=f"risk-extreme-{minute}", minute=minute, level="extreme", riskScore=0.95,
            polygon=scale_polygon(now_poly, 180.0),
            label="Active fire area (modeled)",
            guidance="Modeled active fire. Do not enter. Follow official evacuation orders."))
    p15 = perimeter_polygon(cells, minute + 15)
    if p15:
        zones.append(RiskZone(
            id=f"risk-high-{minute}", minute=minute, level="high", riskScore=0.72,
            polygon=scale_polygon(p15, 60.0),
            label="Predicted spread ~15 min (modeled)",
            guidance="Modeled fire arrival within ~15 minutes. Leave now via a lower-risk route."))
    p30 = perimeter_polygon(cells, minute + 30)
    if p30:
        zones.append(RiskZone(
            id=f"risk-elevated-{minute}", minute=minute, level="elevated", riskScore=0.45,
            polygon=scale_polygon(p30, 60.0),
            label="Predicted spread ~30 min (modeled)",
            guidance="Inside the 30-minute modeled spread envelope. Prepare to evacuate."))
    heavy = next((z for z in smoke if z.densityLevel == "heavy" and "main" in z.id), None)
    if heavy:
        zones.append(RiskZone(
            id=f"risk-smoke-{minute}", minute=minute, level="elevated", riskScore=0.40,
            polygon=heavy.polygon,
            label="Heavy smoke corridor (modeled)",
            guidance="Modeled heavy smoke: low visibility and air hazard. Prefer routes around it."))
    return zones


def run_simulation(params: SimulationRequest,
                   fuel_at: Callable[[float, float], float],
                   slope_fn: Optional[SlopeFn] = None) -> SimulationResult:
    cells = simulate_cells(params, fuel_at, slope_fn)
    is_default = (abs(params.windFromDeg - DEFAULTS.windFromDeg) < 1e-6
                  and abs(params.windSpeedMph - DEFAULTS.windSpeedMph) < 1e-6
                  and abs(params.fireIntensity - DEFAULTS.fireIntensity) < 1e-6)
    replay_source = "historical_demo" if is_default else "predicted"

    minutes = [m for m in TIMELINE_MINUTES if m <= params.horizonMinutes]
    by_minute: Dict[str, List[FireCell]] = {}
    predicted_by_minute: Dict[str, List[FireCell]] = {}
    perimeters: Dict[str, FirePerimeter] = {}
    risk: Dict[str, List[RiskZone]] = {}
    smoke: Dict[str, List[SmokeZone]] = {}
    envelopes: Dict[str, UncertaintyEnvelope] = {}

    for m in minutes:
        key = str(m)
        act = active_cells(cells, m)
        by_minute[key] = [_to_fire_cell(c, m, replay_source, m) for c in act]
        predicted_by_minute[key] = [
            _to_fire_cell(c, c.ignition, "predicted", m)
            for c in cells if m < c.ignition <= m + 20.0
        ]
        poly = perimeter_polygon(cells, m)
        if poly:
            perimeters[key] = FirePerimeter(
                minute=m, polygon=poly, areaSqKm=round(geo.polygon_area_sqkm(poly), 3),
                source="replay_model" if is_default else "predicted",
                confidence=round(max(0.4, 0.95 - 0.004 * m), 2))
        szs = smoke_zones_for_minute(cells, m, params)
        smoke[key] = szs
        risk[key] = _risk_zones(cells, m, params, szs)
        fut = perimeter_polygon(cells, min(params.horizonMinutes, m + 15))
        if fut:
            buf = 80.0 + 9.0 * 15.0
            envelopes[key] = UncertaintyEnvelope(
                minute=m, polygon=scale_polygon(fut, buf), bufferMeters=buf)

    notes = [
        "Cellular fast-marching spread model; rate = base * wind * alignment * fuel * slope * intensity * jitter.",
        f"Wind {params.windSpeedMph:.0f} mph from {params.windFromDeg:.0f}deg; intensity dial {params.fireIntensity:.2f}.",
        f"{len(cells)} cells ignited within the {params.horizonMinutes:.0f}-minute horizon.",
        "Replay layer approximates publicly reported Jan 7, 2025 progression; it is synthetic demo data.",
    ]
    return SimulationResult(
        params=params, minutes=minutes, ignitionPoint=list(IGNITION_LONLAT),
        fireCellsByMinute=by_minute, predictedFireCellsByMinute=predicted_by_minute,
        firePerimeterByMinute=perimeters, riskZonesByMinute=risk,
        smokeZonesByMinute=smoke, uncertaintyEnvelopeByMinute=envelopes,
        modelNotes=notes)
