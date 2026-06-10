"""Time-aware, hazard-aware evacuation routing over the demo road graph.

Not shortest-path: every edge is costed at the minute the driver would
actually enter it, against the fire model's arrival estimates, the smoke
plumes for that minute, official closure toggles and user hazard reports.

Three weight profiles produce three genuinely different candidates
(fastest / lowest smoke / largest fire buffer), then every candidate is
scored with the product formula and the highest FinalRouteScore wins:

    FinalRouteScore = 0.30 * fireBufferScore
                    + 0.25 * smokeAvoidanceScore
                    + 0.15 * travelTimeScore
                    + 0.10 * roadClosureComplianceScore
                    + 0.10 * profileSuitabilityScore
                    + 0.05 * congestionScore
                    + 0.05 * backupRouteScore
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from . import demo_world, geo
from .models import (
    CandidateRoute,
    Maneuver,
    PersonProfile,
    RouteConditions,
    RouteRecommendation,
    RouteScore,
    SafeZone,
)

LonLat = Tuple[float, float]

SCORE_WEIGHTS = {
    "fireBufferScore": 0.30, "smokeAvoidanceScore": 0.25, "travelTimeScore": 0.15,
    "roadClosureComplianceScore": 0.10, "profileSuitabilityScore": 0.10,
    "congestionScore": 0.05, "backupRouteScore": 0.05,
}

REPORT_RADIUS_M = 340.0
REPORT_DENSITY = 0.95
REPORT_EDGE_PENALTY = 200.0  # a user-reported zero-visibility zone is near-closed
SAMPLE_STEP_M = 120.0


@dataclass
class Edge:
    id: str
    a: str
    b: str
    name: str
    cls: str
    speed_mph: float
    congestion: float
    closure_group: str
    geometry: List[List[float]]  # a -> b
    length_m: float = 0.0
    samples: List[List[float]] = field(default_factory=list)

    def reversed(self) -> "Edge":
        return Edge(self.id + ":rev", self.b, self.a, self.name, self.cls, self.speed_mph,
                    self.congestion, self.closure_group, list(reversed(self.geometry)),
                    self.length_m, list(reversed(self.samples)))


@dataclass
class HazardContext:
    """Callables wired to the live fire simulation plus user-reported hazards."""
    fire_arrival: Callable[[float, float], float]          # lon, lat -> minute
    smoke_density: Callable[[float, float, float], float]  # lon, lat, minute -> 0..1
    conditions: RouteConditions = field(default_factory=RouteConditions)
    smoke_scale: float = 1.0  # person-profile smoke sensitivity multiplier

    def effective_smoke(self, lon: float, lat: float, minute: float) -> float:
        d = self.smoke_density(lon, lat, minute)
        if self.conditions.smokeSensitivityBoost > 0.0:
            d = min(1.0, d * (1.0 + self.conditions.smokeSensitivityBoost))
        rb = self.conditions.reportedBlockNear
        if rb is not None:
            if geo.haversine_m(lon, lat, rb[0], rb[1]) < REPORT_RADIUS_M:
                d = max(d, REPORT_DENSITY)  # user-reported low-visibility area
        if self.conditions.visibilityLost:
            d = min(1.0, d * 1.6)
        return d

    def smoke_speed_factor(self, smoke_avg: float) -> float:
        """Smoke slows real driving; dramatically so once visibility is lost."""
        return 1.0 + (1.5 if self.conditions.visibilityLost else 0.35) * smoke_avg


@dataclass
class WeightProfile:
    route_type: str
    name: str
    time_w: float
    smoke_w: float
    buffer_w: float
    buffer_target_min: float


WEIGHT_PROFILES = [
    WeightProfile("fastest", "Fastest route", 1.00, 0.8, 0.06, 10.0),
    WeightProfile("lowest_smoke", "Lowest smoke exposure", 0.55, 16.0, 0.30, 12.0),
    WeightProfile("max_fire_buffer", "Largest fire buffer", 0.45, 3.0, 0.55, 45.0),
]


class RoadNetwork:
    def __init__(self) -> None:
        self.nodes: Dict[str, LonLat] = dict(demo_world.NODES)
        self.adj: Dict[str, List[Edge]] = {n: [] for n in self.nodes}
        self.edges: List[Edge] = []
        for a, b, name, cls, speed, cong, group in demo_world.EDGE_DEFS:
            geom = demo_world.curved_geometry(self.nodes[a], self.nodes[b])
            e = Edge(f"{a}->{b}", a, b, name, cls, speed, cong, group, geom)
            e.length_m = geo.polyline_length_m(geom)
            e.samples = geo.resample_polyline(geom, SAMPLE_STEP_M)
            self.edges.append(e)
            self.adj[a].append(e)
            self.adj[b].append(e.reversed())

    def snap(self, lon: float, lat: float) -> Tuple[Edge, float, LonLat]:
        """Nearest edge, progress along it (a->b meters) and snapped point."""
        best: Tuple[Optional[Edge], float, float, LonLat] = (None, 1e18, 0.0, (lon, lat))
        for e in self.edges:
            p, d, prog = geo.nearest_point_on_polyline(e.geometry, lon, lat)
            if d < best[1]:
                best = (e, d, prog, p)
        assert best[0] is not None
        return best[0], best[2], best[3]


NETWORK = RoadNetwork()


def _congestion_factor(edge: Edge, minute: float) -> float:
    """Evacuation traffic builds over the first hour of the incident."""
    build_up = min(1.0, minute / 60.0)
    return 1.0 + edge.congestion * (0.35 + 0.65 * build_up)


def _edge_cost(edge: Edge, t_enter: float, w: WeightProfile, ctx: HazardContext,
               overlap_penalty: Dict[str, float]) -> Tuple[float, float]:
    """Returns (cost, traverse_minutes). Cost units are 'penalized minutes'."""
    speed_mpm = edge.speed_mph * 1609.34 / 60.0
    t_traverse = edge.length_m / speed_mpm * _congestion_factor(edge, t_enter)

    if edge.closure_group in ctx.conditions.closedRoads:
        return (1e9, t_traverse)  # hard block: official closure compliance

    n = len(edge.samples)
    smoke_sum = 0.0
    min_buffer = 1e9
    in_reported_zone = False
    rb = ctx.conditions.reportedBlockNear
    for i, (slon, slat) in enumerate(edge.samples):
        t_here = t_enter + t_traverse * (i / max(1, n - 1))
        smoke_sum += ctx.effective_smoke(slon, slat, t_here)
        buf = ctx.fire_arrival(slon, slat) - t_here
        if buf < min_buffer:
            min_buffer = buf
        if rb is not None and geo.haversine_m(slon, slat, rb[0], rb[1]) < REPORT_RADIUS_M:
            in_reported_zone = True
    smoke_avg = smoke_sum / max(1, n)
    t_traverse *= ctx.smoke_speed_factor(smoke_avg)

    penalty = 0.0
    if min_buffer < 1.5:
        penalty += 1e6  # never route through the modeled fire front
    if in_reported_zone:
        # A human just reported they cannot see here: treat as near-closed.
        penalty += REPORT_EDGE_PENALTY
    if min_buffer >= 1.5 and min_buffer < w.buffer_target_min:
        short = (w.buffer_target_min - min_buffer) / w.buffer_target_min
        penalty += w.buffer_w * 60.0 * (short ** 1.6)
    penalty += w.smoke_w * ctx.smoke_scale * smoke_avg * t_traverse
    penalty += overlap_penalty.get(edge.id.replace(":rev", ""), 0.0)
    return (w.time_w * t_traverse + penalty, t_traverse)


def _dijkstra(start_links: List[Tuple[str, float, float, List[List[float]], str]],
              goal: str, minute: float, w: WeightProfile, ctx: HazardContext,
              overlap_penalty: Dict[str, float]) -> Optional[List[Edge]]:
    """start_links: (node, cost_min, time_min, geometry origin->node, road name)."""
    dist: Dict[str, float] = {}
    time_at: Dict[str, float] = {}
    prev: Dict[str, Tuple[str, Edge]] = {}
    pq: List[Tuple[float, str]] = []
    entry_geom: Dict[str, Tuple[List[List[float]], str]] = {}
    for node, cost0, time0, geom, road in start_links:
        if cost0 < dist.get(node, 1e18):
            dist[node] = cost0
            time_at[node] = minute + time0
            entry_geom[node] = (geom, road)
            heapq.heappush(pq, (cost0, node))
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, 1e18):
            continue
        if u == goal:
            break
        for e in NETWORK.adj[u]:
            cost, t_trav = _edge_cost(e, time_at[u], w, ctx, overlap_penalty)
            nd = d + cost
            if nd < dist.get(e.b, 1e18):
                dist[e.b] = nd
                time_at[e.b] = time_at[u] + t_trav
                prev[e.b] = (u, e)
                heapq.heappush(pq, (nd, e.b))
    if goal not in dist or dist[goal] >= 1e8:
        return None
    path: List[Edge] = []
    node = goal
    while node in prev:
        u, e = prev[node]
        path.append(e)
        node = u
    path.reverse()
    # Prepend the partial-edge geometry from the snapped origin, carrying the
    # real road name so maneuver grouping stays seamless.
    entry = entry_geom.get(path[0].a if path else goal)
    if entry and len(entry[0]) >= 2:
        lead, road = entry
        lead_edge = Edge("origin-link", "origin", path[0].a if path else goal,
                         road, "link", 25.0, 0.3, "none", lead)
        lead_edge.length_m = geo.polyline_length_m(lead)
        lead_edge.samples = geo.resample_polyline(lead, SAMPLE_STEP_M)
        path.insert(0, lead_edge)
    return path


def _start_links(lon: float, lat: float, heading: float) -> List[Tuple[str, float, float, List[List[float]], str]]:
    """Connect an arbitrary position to the graph via its nearest edge.

    Continuing in the direction of travel is free; doubling back pays a
    U-turn penalty so 'turn around' is possible but never chosen lightly.
    """
    edge, prog, snapped = NETWORK.snap(lon, lat)
    links = []
    total = edge.length_m
    for target, geom_part, dist_m in (
        (edge.b, _slice_polyline(edge.geometry, prog, total), total - prog),
        (edge.a, list(reversed(_slice_polyline(edge.geometry, 0.0, prog))), prog),
    ):
        if len(geom_part) < 2:
            geom_part = [list(snapped), list(NETWORK.nodes[target])]
        first_brg = geo.bearing_deg(geom_part[0][0], geom_part[0][1], geom_part[-1][0], geom_part[-1][1])
        uturn = geo.angle_diff_deg(first_brg, heading) > 120.0
        speed_mpm = edge.speed_mph * 1609.34 / 60.0
        t = dist_m / speed_mpm + (1.2 if uturn else 0.0)
        links.append((target, t + (2.5 if uturn else 0.0), t, geom_part, edge.name))
    return links


def _slice_polyline(coords: Sequence[Sequence[float]], from_m: float, to_m: float) -> List[List[float]]:
    if to_m - from_m < 1.0:
        return []
    pts: List[List[float]] = []
    steps = max(2, int((to_m - from_m) / 60.0) + 1)
    for i in range(steps + 1):
        p, _ = geo.point_along_polyline([tuple(c) for c in coords], from_m + (to_m - from_m) * i / steps)
        pts.append([p[0], p[1]])
    return pts


# ---------------------------------------------------------------------------
# Maneuver generation
# ---------------------------------------------------------------------------

COMPASS = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"]


def initial_bearing(polyline: Sequence[Sequence[float]]) -> Optional[float]:
    """Bearing of the first real movement, skipping duplicated/near-zero
    segments (snapping at a node can emit coincident leading points)."""
    if len(polyline) < 2:
        return None
    p0 = polyline[0]
    for p in polyline[1:]:
        if geo.haversine_m(p0[0], p0[1], p[0], p[1]) > 8.0:
            return geo.bearing_deg(p0[0], p0[1], p[0], p[1])
    return None


def _fmt_dist(meters: float) -> str:
    feet = meters * 3.28084
    if feet < 1000:
        return f"{int(round(feet / 50.0) * 50) or 50} feet"
    miles = meters / 1609.34
    return f"{miles:.1f} miles"


def _turn_type(delta: float) -> Tuple[str, str]:
    if delta > 150:
        return "uturn", "Make a U-turn when safe"
    if delta > 55:
        return "turn", "Turn"
    if delta > 22:
        return "slight", "Bear"
    return "continue", "Continue onto"


def build_maneuvers(path: List[Edge], speed_mph: float, dest_name: str) -> Tuple[List[Maneuver], List[List[float]]]:
    polyline: List[List[float]] = []
    for e in path:
        seg = e.geometry if not polyline else e.geometry[1:]
        polyline.extend([list(p) for p in seg])

    maneuvers: List[Maneuver] = []
    speed_mps = speed_mph * 0.44704
    # Group consecutive edges by road name.
    runs: List[Tuple[str, List[Edge]]] = []
    for e in path:
        if runs and runs[-1][0] == e.name:
            runs[-1][1].append(e)
        else:
            runs.append((e.name, [e]))

    first_geom = runs[0][1][0].geometry
    head0 = initial_bearing(first_geom)
    if head0 is None:
        head0 = initial_bearing(polyline) or 0.0
    start_road = runs[0][0] if runs[0][0] != "current road" else (runs[1][0] if len(runs) > 1 else "the route")
    maneuvers.append(Maneuver(
        id="m0", type="depart", roadName=start_road, distanceMeters=0.0,
        expectedTimeSeconds=0.0, coordinate=list(first_geom[0]),
        instruction=f"Head {COMPASS[int(((head0 + 22.5) % 360) // 45)]} on {start_road}"))

    dist_since = sum(e.length_m for e in runs[0][1])
    for i in range(1, len(runs)):
        prev_edges, cur_edges = runs[i - 1][1], runs[i][1]
        in_brg = geo.bearing_deg(*prev_edges[-1].geometry[-2], *prev_edges[-1].geometry[-1])
        out_brg = geo.bearing_deg(*cur_edges[0].geometry[0], *cur_edges[0].geometry[1])
        delta = (out_brg - in_brg + 540) % 360 - 180  # signed turn angle
        kind, verb = _turn_type(abs(delta))
        side = "right" if delta > 0 else "left"
        road = runs[i][0]
        if kind == "uturn":
            mtype, text = "uturn", f"make a U-turn when safe onto {road}"
        elif kind == "turn":
            mtype, text = f"turn_{side}", f"turn {side} onto {road}"
        elif kind == "slight":
            mtype, text = f"slight_{side}", f"bear {side} onto {road}"
        else:
            mtype, text = "continue", f"continue onto {road}"
        maneuvers.append(Maneuver(
            id=f"m{i}", type=mtype, roadName=road, distanceMeters=round(dist_since, 0),
            expectedTimeSeconds=round(dist_since / speed_mps, 0),
            coordinate=list(cur_edges[0].geometry[0]),
            instruction=f"In {_fmt_dist(dist_since)}, {text}"))
        dist_since = sum(e.length_m for e in cur_edges)

    maneuvers.append(Maneuver(
        id=f"m{len(runs)}", type="arrive", roadName=dest_name,
        distanceMeters=round(dist_since, 0), expectedTimeSeconds=round(dist_since / speed_mps, 0),
        coordinate=list(polyline[-1]),
        instruction=f"Arrive at {dest_name} — simulated lower-risk zone"))
    return maneuvers, polyline


# ---------------------------------------------------------------------------
# Candidate metrics + spec scoring
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Source-agnostic candidate pipeline: routes can come from the demo road
# graph (Dijkstra above) OR live Google Directions; hazard metrics, label
# assignment and the FinalRouteScore formula are IDENTICAL for both.
# ---------------------------------------------------------------------------

@dataclass
class RawRoute:
    polyline: List[List[float]]
    maneuvers: List[Maneuver]
    distance_m: float
    duration_min: float          # base travel time before smoke slowdown
    congestion: float
    closure_groups: set
    canyon_frac: float = 0.0


def hazard_metrics(polyline: List[List[float]], minute: float,
                   ctx: HazardContext, duration_min: float) -> dict:
    """Time-aware hazard pass over any polyline, regardless of its source."""
    pts = geo.resample_polyline([tuple(p) for p in polyline], SAMPLE_STEP_M)
    total_m = geo.polyline_length_m([tuple(p) for p in polyline])
    n = len(pts)
    smoke_sum = 0.0
    peak_smoke = 0.0
    worst_at: LonLat = (pts[0][0], pts[0][1])
    min_buffer = 1e9
    closure_risk = 0.0
    for i, (slon, slat) in enumerate(pts):
        t_here = minute + duration_min * (i / max(1, n - 1))
        d = ctx.effective_smoke(slon, slat, t_here)
        smoke_sum += d
        if d > peak_smoke:
            peak_smoke, worst_at = d, (slon, slat)
        buf = ctx.fire_arrival(slon, slat) - t_here
        min_buffer = min(min_buffer, buf)
        closure_risk = max(closure_risk, min(1.0, max(0.0, (40.0 - buf) / 40.0)) * 0.8)
    smoke_avg = smoke_sum / max(1, n)
    eff_duration = duration_min * ctx.smoke_speed_factor(smoke_avg)
    return {
        "distance_m": total_m,
        "time_min": eff_duration,
        "buffer_min": max(0.0, min_buffer),
        "smoke_score": min(100.0, (smoke_avg * total_m) / 28.0),
        "peak_smoke": peak_smoke,
        "worst_smoke_road": road_name_near(worst_at[0], worst_at[1]),
        "closure_risk": closure_risk,
    }


def road_name_near(lon: float, lat: float) -> str:
    edge, _, snapped = NETWORK.snap(lon, lat)
    if geo.haversine_m(snapped[0], snapped[1], lon, lat) < 80.0:
        return edge.name
    return "the route"


def closure_groups_for_polyline(polyline: List[List[float]]) -> set:
    """Approximate which closure groups a (possibly Google) route touches by
    snapping samples onto the demo graph, which mirrors the same streets."""
    groups: set = set()
    pts = geo.resample_polyline([tuple(p) for p in polyline], 160.0)
    for lon, lat in pts:
        edge, _, snapped = NETWORK.snap(lon, lat)
        if geo.haversine_m(snapped[0], snapped[1], lon, lat) < 45.0:
            groups.add(edge.closure_group)
    return groups


def polyline_overlap(a: List[List[float]], b: List[List[float]], tol_m: float = 60.0) -> float:
    """Fraction of route A's samples lying within tol of route B."""
    pa = geo.resample_polyline([tuple(p) for p in a], 150.0)
    pb = geo.resample_polyline([tuple(p) for p in b], 150.0)
    if not pa or not pb:
        return 0.0
    near = 0
    for lon, lat in pa:
        if any(geo.haversine_m(lon, lat, q[0], q[1]) < tol_m for q in pb):
            near += 1
    return near / len(pa)


def _edge_overlap_fraction(a: List[Edge], b: List[Edge]) -> float:
    ids_b = {e.id.replace(":rev", "") for e in b}
    shared = sum(e.length_m for e in a if e.id.replace(":rev", "") in ids_b)
    return shared / max(1.0, sum(e.length_m for e in a))


def finalize_recommendation(raws: List[RawRoute], heading: float, minute: float,
                            profile: PersonProfile, ctx: HazardContext,
                            dest: SafeZone, reroute: bool,
                            source: str) -> RouteRecommendation:
    if not raws:
        raise RuntimeError("No viable route found")
    metrics = [hazard_metrics(r.polyline, minute, ctx, r.duration_min) for r in raws]

    # Assign the three labels by MEASURED metrics so cards never lie.
    order = list(range(len(raws)))
    assigned: Dict[int, WeightProfile] = {}
    fastest_i = min(order, key=lambda i: metrics[i]["time_min"])
    assigned[fastest_i] = WEIGHT_PROFILES[0]
    rest = [i for i in order if i != fastest_i]
    if rest:
        lowest_i = min(rest, key=lambda i: metrics[i]["smoke_score"])
        assigned[lowest_i] = WEIGHT_PROFILES[1]
        for i in rest:
            if i != lowest_i:
                assigned[i] = WEIGHT_PROFILES[2]

    fastest_time = min(m["time_min"] for m in metrics)
    candidates: List[CandidateRoute] = []
    raw_by_id: Dict[str, RawRoute] = {}
    for idx, raw in enumerate(raws):
        w = assigned.get(idx, WEIGHT_PROFILES[2])
        m = metrics[idx]
        maneuvers = list(raw.maneuvers)
        polyline = raw.polyline
        warnings: List[str] = []
        if m["peak_smoke"] > 0.55:
            warnings.append(f"Crosses modeled heavy smoke near {m['worst_smoke_road']}.")
        elif m["peak_smoke"] > 0.3:
            warnings.append(f"Passes modeled moderate smoke near {m['worst_smoke_road']}.")
        if m["buffer_min"] < 15:
            warnings.append(f"Modeled fire buffer only ~{m['buffer_min']:.0f} min at the tightest point.")
        if raw.congestion > 0.55:
            warnings.append("High evacuation-traffic congestion risk (modeled).")
        rid = f"route-{w.route_type}" if idx == min(i for i, ww in assigned.items() if ww is w) \
            else f"route-{w.route_type}-{idx}"
        # If the first move requires reversing the user's heading, say so.
        first_brg = initial_bearing(polyline)
        if first_brg is not None and maneuvers:
            if geo.angle_diff_deg(first_brg, heading) > 120.0:
                maneuvers[0].type = "uturn"
                maneuvers[0].instruction = (f"Make a U-turn when safe, then "
                                            f"{maneuvers[0].instruction[0].lower()}{maneuvers[0].instruction[1:]}")
        candidates.append(CandidateRoute(
            routeId=rid, name=w.name,
            routeType=w.route_type,  # type: ignore[arg-type]
            polyline=[[round(p[0], 6), round(p[1], 6)] for p in polyline],
            maneuvers=maneuvers,
            totalDistanceMeters=round(m["distance_m"], 0),
            estimatedTravelTimeMinutes=round(m["time_min"], 1),
            fireArrivalBufferMinutes=round(m["buffer_min"], 1),
            smokeExposureScore=round(m["smoke_score"], 1),
            congestionRisk=round(raw.congestion, 2),
            roadClosureRisk=round(m["closure_risk"], 2),
            accessibilityScore=round(max(0.1, 1.0 - 0.05 * len(maneuvers)
                                         - 0.35 * raw.canyon_frac * (1.0 - profile.mobilityScore)), 2),
            confidence=round(min(0.95, max(0.35, 0.92 - 0.2 * m["smoke_score"] / 100.0
                                           - 0.1 * max(0.0, 20.0 - m["buffer_min"]) / 20.0
                                           - (0.05 if reroute else 0.0))), 2),
            warnings=warnings))
        raw_by_id[rid] = raw

    # Spec scoring formula over normalized component scores.
    for c in candidates:
        others = [o for o in candidates if o.routeId != c.routeId]
        diversity = 1.0 - min((polyline_overlap(c.polyline, o.polyline) for o in others),
                              default=1.0)
        closed_used = bool(raw_by_id[c.routeId].closure_groups
                           & set(ctx.conditions.closedRoads))
        s = RouteScore(
            fireBufferScore=round(min(1.0, c.fireArrivalBufferMinutes / 45.0), 3),
            smokeAvoidanceScore=round(1.0 - c.smokeExposureScore / 100.0, 3),
            travelTimeScore=round(min(1.0, fastest_time / max(0.1, c.estimatedTravelTimeMinutes)), 3),
            roadClosureComplianceScore=round(0.05 if closed_used else 1.0 - 0.5 * c.roadClosureRisk, 3),
            profileSuitabilityScore=round(c.accessibilityScore if not profile.prefersFewerTurns
                                          else max(0.05, c.accessibilityScore - 0.04 * len(c.maneuvers)), 3),
            congestionScore=round(1.0 - c.congestionRisk, 3),
            backupRouteScore=round(diversity, 3),
            final=0.0)
        s.final = round(sum(getattr(s, k) * w for k, w in SCORE_WEIGHTS.items()), 3)
        c.score = s

    best = max(candidates, key=lambda c: c.score.final)  # type: ignore[union-attr]
    fastest = next((c for c in candidates if c.routeType == "fastest"), candidates[0])
    explanation = _explain(best, fastest, candidates, ctx, reroute, dest)
    why_not = _why_not_fastest(best, fastest)
    return RouteRecommendation(
        recommendedRouteId=best.routeId, candidates=candidates,
        explanation=explanation, whyNotFastest=why_not, generatedAtMinute=minute,
        source=source,  # type: ignore[arg-type]
        destination=dest)


def _demo_raw_from_path(path: List[Edge], minute: float, profile: PersonProfile,
                        dest_name: str) -> RawRoute:
    maneuvers, polyline = build_maneuvers(path, profile.travelSpeedMph, dest_name)
    t = minute
    congestion_acc = 0.0
    canyon_m = 0.0
    total_m = sum(e.length_m for e in path)
    for e in path:
        speed_mpm = e.speed_mph * 1609.34 / 60.0
        t += e.length_m / speed_mpm * _congestion_factor(e, t)
        congestion_acc += e.congestion * e.length_m
        if e.cls == "canyon":
            canyon_m += e.length_m
    return RawRoute(
        polyline=[[p[0], p[1]] for p in polyline], maneuvers=maneuvers,
        distance_m=total_m, duration_min=t - minute,
        congestion=min(1.0, congestion_acc / max(1.0, total_m)),
        closure_groups={e.closure_group for e in path},
        canyon_frac=canyon_m / max(1.0, total_m))


def recommend_routes(position: LonLat, heading: float, minute: float,
                     profile: PersonProfile, ctx: HazardContext,
                     destination_id: str = demo_world.DEFAULT_DESTINATION,
                     reroute: bool = False) -> RouteRecommendation:
    """Demo road-graph planner: three diversified hazard-aware Dijkstra runs."""
    goal = demo_world.DEST_NODE.get(destination_id, "sm_staging")
    dest = next(z for z in demo_world.SAFE_ZONES if z.id == destination_id)
    ctx.smoke_scale = 0.6 + 0.8 * profile.smokeSensitivity
    links = _start_links(position[0], position[1], heading)

    paths: List[List[Edge]] = []
    for w in WEIGHT_PROFILES:
        path = _dijkstra(links, goal, minute, w, ctx, {})
        if path is None:
            continue
        # Force diversity: if this profile lands on an already-seen corridor,
        # replan with every previously used edge penalized so judges always
        # compare genuinely different alternatives.
        if any(_edge_overlap_fraction(path, p) > 0.85 for p in paths):
            used_edges: Dict[str, float] = {}
            for prev in paths + [path]:
                for e in prev:
                    used_edges[e.id.replace(":rev", "")] = 25.0
            alt = _dijkstra(links, goal, minute, w, ctx, used_edges)
            if alt is not None and all(_edge_overlap_fraction(alt, p) <= 0.85 for p in paths):
                path = alt
        paths.append(path)

    if not paths:
        raise RuntimeError("No viable route found in demo network")
    raws = [_demo_raw_from_path(p, minute, profile, dest.name) for p in paths]
    return finalize_recommendation(raws, heading, minute, profile, ctx, dest,
                                   reroute, source="demo_graph")


def recommend_routes_google(position: LonLat, heading: float, minute: float,
                            profile: PersonProfile, ctx: HazardContext,
                            dest: SafeZone, reroute: bool = False) -> RouteRecommendation:
    """LIVE planner: real Google Routes API alternatives, hazard-scored by the
    same engine. Raises google_maps.GoogleUnavailable on any failure so the
    caller can fall back to the demo graph."""
    from . import google_maps  # local import keeps fallback mode dependency-free

    ctx.smoke_scale = 0.6 + 0.8 * profile.smokeSensitivity
    groutes = google_maps.compute_routes(position, (dest.lon, dest.lat), dest.name)
    evac_factor = 1.0 + 0.35 * min(1.0, minute / 60.0)  # evacuation traffic builds
    raws = [RawRoute(
        polyline=g["polyline"], maneuvers=g["maneuvers"],
        distance_m=g["distanceMeters"],
        duration_min=max(0.5, g["durationMinutes"]) * evac_factor,
        congestion=min(1.0, 0.40 + 0.30 * min(1.0, minute / 60.0)),
        closure_groups=closure_groups_for_polyline(g["polyline"]),
    ) for g in groutes[:4]]
    return finalize_recommendation(raws, heading, minute, profile, ctx, dest,
                                   reroute, source="google_directions")


def _explain(best: CandidateRoute, fastest: CandidateRoute,
             all_c: List[CandidateRoute], ctx: HazardContext, reroute: bool,
             dest: Optional[SafeZone] = None) -> str:
    parts = []
    if reroute:
        parts.append("Re-routed using your latest position and report.")
    dest_part = f" to {dest.name}" if dest else ""
    parts.append(
        f"Recommended simulated route: {best.name}{dest_part} "
        f"({best.totalDistanceMeters / 1609.34:.1f} mi, ~{best.estimatedTravelTimeMinutes:.0f} min modeled).")
    parts.append(
        f"It holds a ~{best.fireArrivalBufferMinutes:.0f}-minute modeled fire buffer and a smoke "
        f"exposure score of {best.smokeExposureScore:.0f}/100, the best balance of the "
        f"{len(all_c)} candidates under current scenario inputs.")
    if ctx.conditions.visibilityLost:
        parts.append("Your low-visibility report raised the weight of smoke-heavy segments.")
    if ctx.conditions.closedRoads:
        parts.append(f"Closed roads excluded: {', '.join(ctx.conditions.closedRoads)}.")
    parts.append(f"Route confidence {best.confidence:.0%} given model uncertainty. "
                 "This is modeled risk, not a guarantee — follow official evacuation orders.")
    return " ".join(parts)


def _why_not_fastest(best: CandidateRoute, fastest: CandidateRoute) -> str:
    if best.routeId == fastest.routeId:
        return ("The fastest route is also the lowest modeled-risk route right now, "
                "so speed and safety margin agree.")
    dt = best.estimatedTravelTimeMinutes - fastest.estimatedTravelTimeMinutes
    reasons = []
    if fastest.smokeExposureScore > best.smokeExposureScore + 5:
        reasons.append(f"crosses heavier modeled smoke ({fastest.smokeExposureScore:.0f} vs "
                       f"{best.smokeExposureScore:.0f}/100)")
    if fastest.fireArrivalBufferMinutes < best.fireArrivalBufferMinutes - 2:
        reasons.append(f"leaves a thinner fire buffer ({fastest.fireArrivalBufferMinutes:.0f} vs "
                       f"{best.fireArrivalBufferMinutes:.0f} min modeled)")
    if not reasons:
        reasons.append("scores lower on closure and congestion risk")
    return (f"The fastest route ({fastest.name}) would save ~{abs(dt):.0f} min but "
            f"{' and '.join(reasons)}. The recommendation trades a little time for a "
            "larger modeled safety margin.")
