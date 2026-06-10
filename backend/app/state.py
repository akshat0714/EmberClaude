"""In-memory scenario session: one simulated resident, one live fire model.

Owns the cached fire simulation (real Google-elevation slopes when a key is
configured), the resident's position along the active route, user-reported
hazard conditions, the latest recommendation, and — central to the live
experience — the DYNAMIC safe-zone destination: every advance re-checks the
predicted spread, and when it encroaches on the active safe zone the
destination relocates and the route re-plans automatically.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from . import demo_world, fire_model, geo, google_maps, route_engine, safe_zones
from .google_config import google_enabled
from .models import (
    AdvanceResult,
    CandidateRoute,
    Maneuver,
    PersonProfile,
    RouteConditions,
    RouteRecommendation,
    SimulationRequest,
    SimulationResult,
    UserPosition,
)


class ScenarioState:
    def __init__(self) -> None:
        self.reset()

    def reset(self, params: Optional[SimulationRequest] = None) -> None:
        self.params = params or SimulationRequest()
        # Real terrain gradients (Google Elevation grid) when available;
        # the analytic twin heightfield otherwise.
        self.slope_fn = google_maps.slope_function(demo_world.SCENE_BOUNDS)
        self.cells = fire_model.simulate_cells(self.params, demo_world.fuel_at, self.slope_fn)
        self.sim: Optional[SimulationResult] = None
        self.profile_id = "standard_adult"
        self.conditions = RouteConditions()
        self.destination_id: Optional[str] = None  # None -> auto-select nearest viable
        self.user = UserPosition(
            lon=demo_world.USER_START[0], lat=demo_world.USER_START[1],
            headingDeg=160.0, minute=0.0, status="idle")
        self.active_route: Optional[CandidateRoute] = None
        self.last_recommendation: Optional[RouteRecommendation] = None
        self._maneuver_progress: List[float] = []

    # -- simulation ---------------------------------------------------------

    def run_simulation(self, params: SimulationRequest) -> SimulationResult:
        if params != self.params or self.sim is None:
            self.params = params
            self.cells = fire_model.simulate_cells(params, demo_world.fuel_at, self.slope_fn)
            self.sim = fire_model.run_simulation(params, demo_world.fuel_at, self.slope_fn)
        return self.sim

    def ensure_sim(self) -> SimulationResult:
        if self.sim is None:
            self.sim = fire_model.run_simulation(self.params, demo_world.fuel_at, self.slope_fn)
        return self.sim

    def profile(self) -> PersonProfile:
        return next((p for p in demo_world.PROFILES if p.id == self.profile_id),
                    demo_world.PROFILES[0])

    # -- hazard lookups for the route engine ---------------------------------

    def fire_arrival(self, lon: float, lat: float) -> float:
        return fire_model.fire_arrival_minute(
            self.cells, lon, lat, self.params, fuel_at=demo_world.fuel_at)

    def _smoke_density(self, lon: float, lat: float, minute: float) -> float:
        sim = self.ensure_sim()
        frame = max((m for m in sim.minutes if m <= minute), default=sim.minutes[0])
        zones = sim.smokeZonesByMinute.get(str(frame), [])
        return fire_model.smoke_density_at(zones, lon, lat)

    def hazard_context(self) -> route_engine.HazardContext:
        return route_engine.HazardContext(
            fire_arrival=self.fire_arrival,
            smoke_density=self._smoke_density,
            conditions=self.conditions)

    # -- dynamic safe-zone destination ----------------------------------------

    def zone_statuses(self, minute: float) -> List[safe_zones.SafeZoneStatus]:
        return safe_zones.evaluate_zones(self.cells, minute, self.fire_arrival)

    def _resolve_destination(self, minute: float,
                             forced_id: Optional[str] = None) -> safe_zones.SafeZoneStatus:
        statuses = self.zone_statuses(minute)
        if forced_id:
            forced = next((s for s in statuses if s.zone.id == forced_id), None)
            if forced is not None:
                self.destination_id = forced.zone.id
                return forced
        if self.destination_id:
            current = next((s for s in statuses if s.zone.id == self.destination_id), None)
            # Stability: keep the active destination until it is compromised,
            # so the plan doesn't oscillate between near-equal zones.
            if current is not None and current.status != "compromised":
                return current
        chosen = safe_zones.select_destination(statuses, (self.user.lon, self.user.lat))
        self.destination_id = chosen.zone.id
        return chosen

    # -- routing --------------------------------------------------------------

    def recommend(self, position: Optional[Tuple[float, float]] = None,
                  heading: Optional[float] = None, minute: Optional[float] = None,
                  destination_id: Optional[str] = None,
                  reroute: bool = False) -> RouteRecommendation:
        if position is not None:
            self.user.lon, self.user.lat = position
        if heading is not None:
            self.user.headingDeg = heading
        if minute is not None:
            self.user.minute = minute
        dest_status = self._resolve_destination(self.user.minute, destination_id)
        zone = dest_status.zone

        rec: Optional[RouteRecommendation] = None
        if google_enabled():
            try:
                rec = route_engine.recommend_routes_google(
                    (self.user.lon, self.user.lat), self.user.headingDeg,
                    self.user.minute, self.profile(), self.hazard_context(),
                    zone, reroute=reroute)
            except google_maps.GoogleUnavailable:
                rec = None  # fall through to the demo graph
        if rec is None:
            rec = route_engine.recommend_routes(
                (self.user.lon, self.user.lat), self.user.headingDeg, self.user.minute,
                self.profile(), self.hazard_context(), zone.id, reroute=reroute)
        self.last_recommendation = rec
        self.set_active_route(rec.recommendedRouteId)
        return rec

    def set_active_route(self, route_id: str) -> Optional[CandidateRoute]:
        if not self.last_recommendation:
            return None
        route = next((c for c in self.last_recommendation.candidates
                      if c.routeId == route_id), None)
        if route:
            self.active_route = route
            self.user.routeId = route.routeId
            self.user.routeProgressMeters = 0.0
            self.user.onRoute = True
            self.user.status = "enroute"
            poly = [tuple(p) for p in route.polyline]
            self._maneuver_progress = [
                geo.nearest_point_on_polyline(poly, m.coordinate[0], m.coordinate[1])[2]
                for m in route.maneuvers]
        return route

    # -- user movement ---------------------------------------------------------

    def advance(self, meters: float, minute: Optional[float] = None) -> AdvanceResult:
        if minute is not None:
            self.user.minute = max(self.user.minute, minute)
        route = self.active_route
        if route is not None and self.user.status != "arrived":
            poly = [tuple(p) for p in route.polyline]
            total = geo.polyline_length_m(poly)
            speed_mpm = self.profile().travelSpeedMph * 1609.34 / 60.0
            self.user.routeProgressMeters = min(total, self.user.routeProgressMeters + meters)
            self.user.minute += meters / speed_mpm
            (lon, lat), hdg = geo.point_along_polyline(poly, self.user.routeProgressMeters)
            self.user.lon, self.user.lat, self.user.headingDeg = lon, lat, hdg
            self.user.onRoute = True
            if self.user.routeProgressMeters >= total - 20.0:
                self.user.status = "arrived"
        result = self._status_result()
        return self._watch_safe_zone(result)

    def _watch_safe_zone(self, result: AdvanceResult) -> AdvanceResult:
        """The core live-mode loop: if the predicted spread zone now reaches
        the active safe zone, MOVE the safe zone and re-route immediately."""
        if self.destination_id is None or self.active_route is None:
            return result
        statuses = self.zone_statuses(self.user.minute)
        current = next((s for s in statuses if s.zone.id == self.destination_id), None)
        if current is None:
            return result
        result.destination = current.zone
        if current.status != "compromised":
            return result
        others = [s for s in statuses if s.zone.id != current.zone.id]
        replacement = safe_zones.select_destination(others, (self.user.lon, self.user.lat))
        if replacement.zone.id == current.zone.id:
            return result
        old_name = current.zone.name
        self.destination_id = replacement.zone.id
        rec = self.recommend(reroute=True)
        fresh = self._status_result()
        fresh.destination = replacement.zone
        fresh.safeZoneChanged = True
        fresh.safeZoneNote = (
            f"{old_name} is now inside the modeled predicted spread zone. "
            f"Redirecting to {replacement.zone.name} and re-routing. "
            "Follow official evacuation orders.")
        fresh.recommendation = rec
        fresh.arrived = False
        return fresh

    def _status_result(self) -> AdvanceResult:
        route = self.active_route
        user = self.user
        if route is None:
            return AdvanceResult(position=user, currentInstruction="No active route yet.",
                                 arrived=False)
        poly = [tuple(p) for p in route.polyline]
        total = geo.polyline_length_m(poly)
        next_m: Optional[Maneuver] = None
        dist_to = 0.0
        for m, prog in zip(route.maneuvers, self._maneuver_progress):
            if m.type == "depart":
                continue
            if prog > user.routeProgressMeters + 8.0:
                next_m, dist_to = m, prog - user.routeProgressMeters
                break
        if next_m is None and route.maneuvers:
            next_m = route.maneuvers[-1]
            dist_to = max(0.0, total - user.routeProgressMeters)

        # Remaining modeled fire buffer over the rest of the route.
        ctx = self.hazard_context()
        speed_mpm = self.profile().travelSpeedMph * 1609.34 / 60.0
        remaining = max(0.0, total - user.routeProgressMeters)
        buffer_min = 1e9
        steps = max(2, int(remaining / 200.0) + 1)
        for i in range(steps):
            d = user.routeProgressMeters + remaining * i / max(1, steps - 1)
            (plon, plat), _ = geo.point_along_polyline(poly, d)
            t_here = user.minute + (d - user.routeProgressMeters) / speed_mpm
            buffer_min = min(buffer_min, ctx.fire_arrival(plon, plat) - t_here)
        smoke_here = ctx.effective_smoke(user.lon, user.lat, user.minute)

        arrived = user.status == "arrived"
        instruction = ("You have reached the simulated lower-risk zone. Continue to follow "
                       "official emergency guidance." if arrived else
                       (next_m.instruction if next_m else "Continue on the highlighted route."))
        dest = (self.last_recommendation.destination
                if self.last_recommendation else None)
        return AdvanceResult(
            position=user, currentInstruction=instruction,
            nextManeuver=None if arrived else next_m,
            distanceToManeuverMeters=round(dist_to, 0),
            remainingDistanceMeters=round(remaining, 0),
            remainingBufferMinutes=round(max(0.0, min(buffer_min, 240.0)), 1),
            smokeDensityHere=round(smoke_here, 2),
            arrived=arrived,
            destination=dest)

    def deviate(self, mode: str) -> UserPosition:
        """Push the simulated user off-plan to exercise re-routing."""
        user = self.user
        route = self.active_route
        if mode == "missed_turn" and route is not None:
            # Overshoot the next turn: keep the incoming heading past the junction.
            poly = [tuple(p) for p in route.polyline]
            nxt = None
            for m, prog in zip(route.maneuvers, self._maneuver_progress):
                if m.type in ("depart", "arrive"):
                    continue
                if prog > user.routeProgressMeters + 5.0:
                    nxt = (m, prog)
                    break
            if nxt is not None:
                (jlon, jlat), in_hdg = geo.point_along_polyline(poly, max(0.0, nxt[1] - 5.0))
                lon, lat = geo.destination(jlon, jlat, in_hdg, 130.0)
                user.lon, user.lat, user.headingDeg = lon, lat, in_hdg
                user.routeProgressMeters = nxt[1]
            else:
                lon, lat = geo.destination(user.lon, user.lat, user.headingDeg, 130.0)
                user.lon, user.lat = lon, lat
        elif mode == "blocked":
            ahead = geo.destination(user.lon, user.lat, user.headingDeg, 160.0)
            self.conditions.reportedBlockNear = [ahead[0], ahead[1]]
        else:  # off_route
            lon, lat = geo.destination(user.lon, user.lat, user.headingDeg + 75.0, 140.0)
            user.lon, user.lat = lon, lat
        user.onRoute = mode == "blocked"
        if mode != "blocked":
            user.status = "off_route"
        return user

    def report_visibility_lost(self) -> None:
        self.conditions.visibilityLost = True
        self.conditions.smokeSensitivityBoost = max(self.conditions.smokeSensitivityBoost, 0.5)
        ahead = geo.destination(self.user.lon, self.user.lat, self.user.headingDeg, 280.0)
        self.conditions.reportedBlockNear = [ahead[0], ahead[1]]


STATE = ScenarioState()
