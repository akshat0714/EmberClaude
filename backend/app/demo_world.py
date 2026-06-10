"""Synthetic-but-plausible world model of Pacific Palisades for the demo.

Road topology, junction coordinates and place names approximate the real
neighborhood (Sunset Blvd, Palisades Dr, Temescal Canyon Rd, Chautauqua
Blvd, PCH, San Vicente Blvd). Geometry is hand-laid DEMO data — close
enough to be recognizable, NOT survey accurate, and never to be used for
real navigation. Buildings and vegetation are procedurally generated,
deterministic, and labeled synthetic.
"""

from __future__ import annotations

import math
import random
from typing import Dict, List, Tuple

from . import geo
from .models import PersonProfile, SafeZone

LonLat = Tuple[float, float]

# ---------------------------------------------------------------------------
# Road graph nodes (approximate junction coordinates)
# ---------------------------------------------------------------------------

NODES: Dict[str, LonLat] = {
    # Pacific Coast Highway, NW -> SE
    "pch_sunset":       (-118.5565, 34.0405),
    "pch_willrogers":   (-118.5455, 34.0382),
    "pch_temescal":     (-118.5345, 34.0365),
    "pch_potrero":      (-118.5260, 34.0340),
    "pch_chautauqua":   (-118.5188, 34.0322),
    "pch_entrada":      (-118.5155, 34.0290),
    "pch_ocean":        (-118.5080, 34.0235),
    "pch_incline":      (-118.5040, 34.0190),
    "sm_staging":       (-118.5005, 34.0155),
    # Sunset Blvd, W -> E
    "sunset_castell":   (-118.5520, 34.0438),
    "sunset_palihigh":  (-118.5410, 34.0452),
    "sunset_temescal":  (-118.5275, 34.0455),
    "sunset_palisdr":   (-118.5232, 34.0458),
    "sunset_via":       (-118.5210, 34.0432),
    "sunset_chautqa":   (-118.5190, 34.0385),
    "sunset_amalfi":    (-118.5120, 34.0415),
    "sunset_riviera":   (-118.5035, 34.0452),
    "sunset_allenford": (-118.4885, 34.0510),
    # Palisades Drive climbing into the Highlands
    "palisdr_1":        (-118.5260, 34.0520),
    "palisdr_2":        (-118.5310, 34.0572),
    "palisdr_3":        (-118.5360, 34.0622),
    "highlands_ctr":    (-118.5395, 34.0660),
    "palisdr_top":      (-118.5430, 34.0712),
    # Canyon connectors
    "temescal_mid":     (-118.5308, 34.0408),
    "chautqa_mid":      (-118.5186, 34.0352),
    # Inland corridor (San Vicente)
    "allenford_sanvic": (-118.4905, 34.0455),
    "sanvic_26th":      (-118.5000, 34.0395),
    "sanvic_7th":       (-118.5085, 34.0330),
    "ocean_sanvic":     (-118.5125, 34.0285),
}

# (a, b, road name, class, speed mph, congestion risk 0..1, closure group)
EDGE_DEFS: List[Tuple[str, str, str, str, float, float, str]] = [
    ("pch_sunset", "pch_willrogers", "Pacific Coast Highway", "highway", 42, 0.45, "pch_north"),
    ("pch_willrogers", "pch_temescal", "Pacific Coast Highway", "highway", 42, 0.45, "pch_north"),
    ("pch_temescal", "pch_potrero", "Pacific Coast Highway", "highway", 40, 0.50, "pch_south"),
    ("pch_potrero", "pch_chautauqua", "Pacific Coast Highway", "highway", 40, 0.50, "pch_south"),
    ("pch_chautauqua", "pch_entrada", "Pacific Coast Highway", "highway", 40, 0.55, "pch_south"),
    ("pch_entrada", "pch_ocean", "Pacific Coast Highway", "highway", 40, 0.55, "pch_south"),
    ("pch_ocean", "pch_incline", "Pacific Coast Highway", "highway", 38, 0.60, "pch_south"),
    ("pch_incline", "sm_staging", "Pacific Coast Highway", "highway", 35, 0.60, "pch_south"),
    ("pch_sunset", "sunset_castell", "Sunset Boulevard", "arterial", 30, 0.50, "sunset_west"),
    ("sunset_castell", "sunset_palihigh", "Sunset Boulevard", "arterial", 30, 0.50, "sunset_west"),
    ("sunset_palihigh", "sunset_temescal", "Sunset Boulevard", "arterial", 30, 0.55, "sunset_west"),
    ("sunset_temescal", "sunset_palisdr", "Sunset Boulevard", "arterial", 28, 0.60, "sunset_village"),
    ("sunset_palisdr", "sunset_via", "Sunset Boulevard", "arterial", 28, 0.60, "sunset_village"),
    ("sunset_via", "sunset_chautqa", "Sunset Boulevard", "arterial", 28, 0.60, "sunset_village"),
    ("sunset_chautqa", "sunset_amalfi", "Sunset Boulevard", "arterial", 30, 0.70, "sunset_east"),
    ("sunset_amalfi", "sunset_riviera", "Sunset Boulevard", "arterial", 30, 0.70, "sunset_east"),
    ("sunset_riviera", "sunset_allenford", "Sunset Boulevard", "arterial", 30, 0.70, "sunset_east"),
    ("sunset_palisdr", "palisdr_1", "Palisades Drive", "canyon", 34, 0.35, "palisades_dr"),
    ("palisdr_1", "palisdr_2", "Palisades Drive", "canyon", 34, 0.35, "palisades_dr"),
    ("palisdr_2", "palisdr_3", "Palisades Drive", "canyon", 34, 0.35, "palisades_dr"),
    ("palisdr_3", "highlands_ctr", "Palisades Drive", "canyon", 32, 0.35, "palisades_dr"),
    ("highlands_ctr", "palisdr_top", "Palisades Drive", "canyon", 30, 0.30, "palisades_dr"),
    ("sunset_temescal", "temescal_mid", "Temescal Canyon Road", "canyon", 30, 0.35, "temescal"),
    ("temescal_mid", "pch_temescal", "Temescal Canyon Road", "canyon", 30, 0.35, "temescal"),
    ("sunset_chautqa", "chautqa_mid", "Chautauqua Boulevard", "canyon", 27, 0.55, "chautauqua"),
    ("chautqa_mid", "pch_chautauqua", "Chautauqua Boulevard", "canyon", 27, 0.55, "chautauqua"),
    ("sunset_allenford", "allenford_sanvic", "Allenford Avenue", "residential", 26, 0.45, "inland"),
    ("allenford_sanvic", "sanvic_26th", "San Vicente Boulevard", "arterial", 33, 0.50, "inland"),
    ("sanvic_26th", "sanvic_7th", "San Vicente Boulevard", "arterial", 33, 0.50, "inland"),
    ("sanvic_7th", "ocean_sanvic", "San Vicente Boulevard", "arterial", 32, 0.55, "inland"),
    ("ocean_sanvic", "pch_incline", "Ocean Avenue / California Incline", "arterial", 28, 0.60, "inland"),
]

CLOSURE_GROUPS = ["pch_north", "pch_south", "sunset_west", "sunset_village",
                  "sunset_east", "temescal", "chautauqua", "palisades_dr", "inland"]

USER_START: LonLat = (-118.5392, 34.0648)  # Palisades Highlands, on Palisades Dr
SCENE_CENTER: LonLat = (-118.527, 34.043)
SCENE_BOUNDS = [-118.60, 33.995, -118.435, 34.105]  # west, south, east, north


def curved_geometry(a: LonLat, b: LonLat, amp_m: float = 18.0, step_m: float = 90.0) -> List[List[float]]:
    """Densify a straight edge and bow it gently so streets read naturally.

    Deterministic per endpoint pair; routing and rendering share this exact
    geometry so the blue dot always sits on the drawn road.
    """
    length = geo.haversine_m(a[0], a[1], b[0], b[1])
    n = max(2, int(length / step_m) + 1)
    brg = geo.bearing_deg(a[0], a[1], b[0], b[1])
    phase = geo.hash_noise(a[0] * 1000, b[1] * 1000) * math.pi * 2
    pts: List[List[float]] = []
    for i in range(n + 1):
        f = i / n
        lon = a[0] + (b[0] - a[0]) * f
        lat = a[1] + (b[1] - a[1]) * f
        off = math.sin(f * math.pi) * math.sin(f * 5.1 + phase) * amp_m
        p = geo.destination(lon, lat, brg + 90, off)
        pts.append([round(p[0], 6), round(p[1], 6)])
    pts[0] = [a[0], a[1]]
    pts[-1] = [b[0], b[1]]
    return pts


# ---------------------------------------------------------------------------
# Vegetation / fuel zones (synthetic polygons, fuelLoad 0..1)
# ---------------------------------------------------------------------------

def _blob(center: LonLat, r_m: float, n: int = 10, wobble: float = 0.35, seed: float = 1.0) -> List[List[float]]:
    pts = []
    for i in range(n):
        ang = 360.0 * i / n
        rr = r_m * (1.0 + wobble * (geo.hash_noise(seed + i, seed * 3.7) - 0.5) * 2)
        p = geo.destination(center[0], center[1], ang, rr)
        pts.append([round(p[0], 6), round(p[1], 6)])
    pts.append(pts[0])
    return pts


VEGETATION_ZONES: List[dict] = [
    {"id": "veg_rustic_canyon", "name": "Rustic Canyon brush (synthetic)", "kind": "canyon_brush",
     "fuelLoad": 0.60, "polygon": [[-118.5200, 34.0335], [-118.5128, 34.0335], [-118.5122, 34.0502],
                                   [-118.5198, 34.0502], [-118.5200, 34.0335]]},
    {"id": "veg_village", "name": "Village landscaping (synthetic)", "kind": "urban_landscaping",
     "fuelLoad": 0.30, "polygon": [[-118.5330, 34.0340], [-118.5130, 34.0340], [-118.5110, 34.0470],
                                   [-118.5320, 34.0480], [-118.5330, 34.0340]]},
    {"id": "veg_highlands", "name": "Highlands irrigated residential (synthetic)", "kind": "urban_landscaping",
     "fuelLoad": 0.35, "polygon": [[-118.5440, 34.0560], [-118.5330, 34.0560], [-118.5300, 34.0640],
                                   [-118.5360, 34.0700], [-118.5450, 34.0680], [-118.5440, 34.0560]]},
    {"id": "veg_temescal_ridge", "name": "Temescal Ridge chaparral (synthetic)", "kind": "chaparral",
     "fuelLoad": 0.95, "polygon": _blob((-118.5450, 34.0640), 2300, 12, 0.30, 11)},
    {"id": "veg_santa_ynez", "name": "Santa Ynez Canyon chaparral (synthetic)", "kind": "chaparral",
     "fuelLoad": 0.90, "polygon": _blob((-118.5230, 34.0690), 2000, 12, 0.32, 23)},
    {"id": "veg_will_rogers", "name": "Will Rogers / Rivas Canyon brush (synthetic)", "kind": "chaparral",
     "fuelLoad": 0.85, "polygon": _blob((-118.5030, 34.0530), 1600, 11, 0.30, 31)},
    {"id": "veg_topanga_edge", "name": "Topanga edge chaparral (synthetic)", "kind": "chaparral",
     "fuelLoad": 0.95, "polygon": _blob((-118.5720, 34.0560), 2100, 11, 0.28, 41)},
    {"id": "veg_temescal_canyon", "name": "Temescal Canyon corridor (synthetic)", "kind": "canyon_brush",
     "fuelLoad": 0.80, "polygon": [[-118.5370, 34.0380], [-118.5270, 34.0400], [-118.5250, 34.0480],
                                   [-118.5350, 34.0470], [-118.5370, 34.0380]]},
    {"id": "veg_coastal_bluff", "name": "Coastal bluff scrub (synthetic)", "kind": "scrub",
     "fuelLoad": 0.45, "polygon": [[-118.5600, 34.0395], [-118.5180, 34.0290], [-118.5080, 34.0210],
                                   [-118.5120, 34.0260], [-118.5500, 34.0420], [-118.5600, 34.0430],
                                   [-118.5600, 34.0395]]},
]


def fuel_at(lon: float, lat: float) -> float:
    """Fuel load lookup: 0 over water, zone value inland, 0.55 default brush."""
    if lat <= geo.coast_lat(lon):
        return 0.0
    for zone in VEGETATION_ZONES:  # village landscaping listed first wins overlaps
        if geo.point_in_polygon(lon, lat, zone["polygon"]):
            return zone["fuelLoad"]
    return 0.55


# ---------------------------------------------------------------------------
# Safe zones / shelters and person profiles
# ---------------------------------------------------------------------------

SAFE_ZONES: List[SafeZone] = [
    SafeZone(id="santa_monica_staging", name="Santa Monica staging area (demo)",
             lon=-118.5005, lat=34.0155, kind="staging",
             notes="Simulated lower-risk assembly point near Ocean Ave; demo destination."),
    SafeZone(id="westwood_rec_center", name="Westwood Recreation Center (approx. location)",
             lon=-118.4480, lat=34.0561, kind="evacuation_center",
             notes="Real evacuation center used Jan 7, 2025; position approximate, off map edge."),
    SafeZone(id="will_rogers_beach_lot", name="Will Rogers Beach lot (demo, last resort)",
             lon=-118.5350, lat=34.0358, kind="refuge",
             notes="Coastal refuge of last resort in the simulation; downwind of modeled smoke."),
]

DEFAULT_DESTINATION = "santa_monica_staging"
DEST_NODE = {"santa_monica_staging": "sm_staging",
             "westwood_rec_center": "sunset_allenford",
             "will_rogers_beach_lot": "pch_temescal"}

PROFILES: List[PersonProfile] = [
    PersonProfile(id="standard_adult", name="Sample Resident (vehicle)",
                  description="Adult evacuating by car; baseline demo profile.",
                  travelSpeedMph=26, smokeSensitivity=0.5, mobilityScore=0.9),
    PersonProfile(id="limited_mobility", name="Limited-mobility resident",
                  description="Needs simpler maneuvers and gentler roads; higher smoke sensitivity.",
                  travelSpeedMph=22, smokeSensitivity=0.7, mobilityScore=0.4,
                  prefersFewerTurns=True),
    PersonProfile(id="family_children", name="Family with children",
                  description="Higher smoke sensitivity, moderate speed.",
                  travelSpeedMph=24, smokeSensitivity=0.8, mobilityScore=0.7),
    PersonProfile(id="first_responder", name="First responder (reference)",
                  description="Reference profile; tolerates smoke, prioritizes time.",
                  travelSpeedMph=35, smokeSensitivity=0.2, mobilityScore=1.0),
]


# ---------------------------------------------------------------------------
# Procedural buildings + visual residential streets (synthetic)
# ---------------------------------------------------------------------------

def _house(rng: random.Random, lon: float, lat: float, rot: float,
           w: float, d: float, h: float, kind: str) -> dict:
    corners = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        p = geo.destination(lon, lat, rot, sy * d / 2)
        p = geo.destination(p[0], p[1], rot + 90, sx * w / 2)
        corners.append([round(p[0], 6), round(p[1], 6)])
    corners.append(corners[0])
    return {"type": "Feature",
            "properties": {"heightM": round(h, 1), "kind": kind, "synthetic": True},
            "geometry": {"type": "Polygon", "coordinates": [corners]}}


def generate_buildings(seed: int = 7) -> dict:
    rng = random.Random(seed)
    feats: List[dict] = []

    # Village grid ("alphabet streets"): rows of homes along N-S streets.
    for sx in range(12):
        s_lon = -118.5310 + sx * 0.00165
        for i in range(26):
            lat = 34.0352 + i * 0.00042
            if rng.random() < 0.16:
                continue
            for side in (-1, 1):
                lon = s_lon + side * 0.00038
                near_sunset = lat > 34.0438
                h = rng.uniform(9.0, 14.0) if (near_sunset and rng.random() < 0.4) else rng.uniform(4.0, 8.5)
                feats.append(_house(rng, lon + rng.uniform(-2e-5, 2e-5), lat + rng.uniform(-5e-5, 5e-5),
                                    rng.uniform(-6, 6), rng.uniform(10, 16), rng.uniform(8, 13), h,
                                    "commercial" if h > 9 else "residence"))

    # Highlands clusters along Palisades Drive.
    spine = ["palisdr_1", "palisdr_2", "palisdr_3", "highlands_ctr", "palisdr_top"]
    for ni, node in enumerate(spine):
        lon0, lat0 = NODES[node]
        for k in range(34):
            ang = rng.uniform(0, 360)
            dist = rng.uniform(70, 330)
            p = geo.destination(lon0, lat0, ang, dist)
            feats.append(_house(rng, p[0], p[1], rng.uniform(0, 180),
                                rng.uniform(11, 17), rng.uniform(9, 14),
                                rng.uniform(4.5, 9.0), "residence"))

    # Castellammare bluff homes near Sunset/PCH.
    lon0, lat0 = NODES["sunset_castell"]
    for k in range(40):
        p = geo.destination(lon0, lat0, rng.uniform(120, 300), rng.uniform(60, 420))
        feats.append(_house(rng, p[0], p[1], rng.uniform(0, 180),
                            rng.uniform(10, 16), rng.uniform(8, 12), rng.uniform(4, 8), "residence"))

    return {"type": "FeatureCollection",
            "properties": {"disclaimer": "Synthetic demo building footprints — not real parcels.",
                           "count": len(feats)},
            "features": feats}


def generate_roads() -> dict:
    feats: List[dict] = []
    for a, b, name, cls, speed, cong, group in EDGE_DEFS:
        feats.append({
            "type": "Feature",
            "properties": {"name": name, "class": cls, "speedMph": speed,
                           "congestionRisk": cong, "closureGroup": group,
                           "approximate": True},
            "geometry": {"type": "LineString",
                         "coordinates": curved_geometry(NODES[a], NODES[b])}})
    # Visual-only residential grid in the village.
    for sx in range(12):
        s_lon = -118.5310 + sx * 0.00165
        feats.append({
            "type": "Feature",
            "properties": {"name": "", "class": "residential_visual", "speedMph": 25,
                           "congestionRisk": 0.2, "closureGroup": "none", "approximate": True},
            "geometry": {"type": "LineString",
                         "coordinates": [[round(s_lon, 6), 34.0348], [round(s_lon, 6), 34.0462]]}})
    return {"type": "FeatureCollection",
            "properties": {"disclaimer": "Approximate demo road geometry — not for navigation."},
            "features": feats}


def generate_vegetation() -> dict:
    feats = [{"type": "Feature",
              "properties": {"id": z["id"], "name": z["name"], "kind": z["kind"],
                             "fuelLoad": z["fuelLoad"], "synthetic": True},
              "geometry": {"type": "Polygon", "coordinates": [z["polygon"]]}}
             for z in VEGETATION_ZONES]
    return {"type": "FeatureCollection",
            "properties": {"disclaimer": "Synthetic fuel/vegetation zones for the demo fire model."},
            "features": feats}
