"""In-memory scenario session: one simulated resident, one live fire model.

Holds the cached fire simulation (recomputed when scenario dials change),
the user's position along the active route, hazard conditions reported by
the user, and the latest route recommendation. v1 is a single demo
session; swap for per-session storage when multi-user support lands.
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

from . import demo_world, fire_model, geo, route_engine
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
        self.cells = fire_model.simulate_cells(self.params, demo_world.fuel_at)
        self.sim: Optional[SimulationResult] = None
        self.profile_id = "standard_adult"
        self.conditions = RouteConditions()
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
            self.cells = fire_model.simulate_cells(params, demo_world.fuel_at)
            self.sim = fire_model.run_simulation(params, demo_world.fuel_at)
        return self.sim

    def ensure_sim(self) -> SimulationResult:
        if self.sim is None:
            self.sim = fire_model.run_simulation(self.params, demo_world.fuel_at)
        return self.sim

    def profile(self) -> PersonProfile:
        return next((p for p in demo_world.PROFILES if p.id == self.profile_id),
                    demo_world.PROFILES[0])

    # -- hazard lookups for the route engine ---------------------------------

    def _smoke_density(self, lon: float, lat: float, minute: float) -> float:
        sim = self.ensure_sim()
        frame = max((m for m in sim.minutes if m <= minute), default=sim.minutes[0])
        zones = sim.smokeZonesByMinute.get(str(frame), [])
        return fire_model.smoke_density_at(zones, lon, lat)

    def hazard_context(self) -> route_engine.HazardContext:
        return route_engine.HazardContext(
            fire_arrival=lambda lon, lat: fire_model.fire_arrival_minute(
                self.cells, lon, lat, self.params, fuel_at=demo_world.fuel_at),
            smoke_density=self._smoke_density,
            conditions=self.conditions)

    # -- routing --------------------------------------------------------------

    def recommend(self, position: Optional[Tuple[float, float]] = None,
                  heading: Optional[float] = None, minute: Optional[float] = None,
                  destination_id: str = demo_world.DEFAULT_DESTINATION,
                  reroute: bool = False) -> RouteRecommendation:
        if position is not None:
            self.user.lon, self.user.lat = position
        if heading is not None:
            self.user.headingDeg = heading
        if minute is not None:
            self.user.minute = minute
        rec = route_engine.recommend_routes(
            (self.user.lon, self.user.lat), self.user.headingDeg, self.user.minute,
            self.profile(), self.hazard_context(), destination_id, reroute=reroute)
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

    def advance(self, meters: float) -> AdvanceResult:
        route = self.active_route
        if route is None or self.user.status == "arrived":
            return self._status_result()
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
        return self._status_result()

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
        return AdvanceResult(
            position=user, currentInstruction=instruction,
            nextManeuver=None if arrived else next_m,
            distanceToManeuverMeters=round(dist_to, 0),
            remainingDistanceMeters=round(remaining, 0),
            remainingBufferMinutes=round(max(0.0, min(buffer_min, 240.0)), 1),
            smokeDensityHere=round(smoke_here, 2),
            arrived=arrived)

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
