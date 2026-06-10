"""Route engine behavior: hazard awareness, closures, deviation re-routing."""

from fastapi.testclient import TestClient

from app import demo_world, geo, route_engine
from app.main import app
from app.state import STATE

client = TestClient(app)

START = list(demo_world.USER_START)


def _recommend(**overrides):
    body = {"position": START, "headingDeg": 160.0, "minute": 12.0,
            "profileId": "standard_adult", "conditions": {}}
    body.update(overrides)
    r = client.post("/routes/recommend", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _route(rec, route_id):
    return next(c for c in rec["candidates"] if c["routeId"] == route_id)


def test_three_distinct_candidates_with_scores():
    rec = _recommend()
    assert len(rec["candidates"]) == 3
    types = {c["routeType"] for c in rec["candidates"]}
    assert types == {"fastest", "lowest_smoke", "max_fire_buffer"}
    for c in rec["candidates"]:
        assert c["score"] is not None
        assert 0.0 <= c["score"]["final"] <= 1.0
        assert len(c["maneuvers"]) >= 2
        assert c["maneuvers"][-1]["type"] == "arrive"


def test_high_smoke_sensitivity_changes_route_preference():
    # Mechanism level: with identical hazards, a smoke-sensitive context must
    # price a smoky edge higher than a smoke-tolerant one.
    smoky_edge = max(route_engine.NETWORK.edges, key=lambda e: e.length_m)
    ctx_lo = route_engine.HazardContext(
        fire_arrival=lambda lon, lat: 240.0,
        smoke_density=lambda lon, lat, m: 0.8,
        smoke_scale=0.6 + 0.8 * 0.2)   # first-responder sensitivity
    ctx_hi = route_engine.HazardContext(
        fire_arrival=lambda lon, lat: 240.0,
        smoke_density=lambda lon, lat, m: 0.8,
        smoke_scale=0.6 + 0.8 * 0.8)   # family-with-children sensitivity
    w = route_engine.WEIGHT_PROFILES[1]  # lowest-smoke planner weights
    cost_lo, _ = route_engine._edge_cost(smoky_edge, 16.0, w, ctx_lo, {})
    cost_hi, _ = route_engine._edge_cost(smoky_edge, 16.0, w, ctx_hi, {})
    assert cost_hi > cost_lo * 1.15, "smoke-sensitive profile must penalize smoke harder"

    # System level: card labels must be truthful — "lowest smoke" is the
    # cleanest of the non-fastest alternatives, by measured metrics.
    rec = _recommend(minute=16.0, profileId="family_children")
    fastest = next(c for c in rec["candidates"] if c["routeType"] == "fastest")
    lowest = next(c for c in rec["candidates"] if c["routeType"] == "lowest_smoke")
    others = [c for c in rec["candidates"] if c["routeId"] != fastest["routeId"]]
    assert lowest["smokeExposureScore"] == min(c["smokeExposureScore"] for c in others)
    assert fastest["estimatedTravelTimeMinutes"] == min(
        c["estimatedTravelTimeMinutes"] for c in rec["candidates"])


def test_road_closure_changes_route_choice():
    baseline = _recommend()
    best = _route(baseline, baseline["recommendedRouteId"])
    used_groups = _groups_for_polyline(best["polyline"])
    closable = next(g for g in ("chautauqua", "temescal", "pch_south", "sunset_east")
                    if g in used_groups)
    closed = _recommend(conditions={"closedRoads": [closable]})
    new_best = _route(closed, closed["recommendedRouteId"])
    assert closable not in _groups_for_polyline(new_best["polyline"]), (
        f"recommended route must comply with closure of {closable}")


def _groups_for_polyline(polyline):
    groups = set()
    for pt in polyline[:: max(1, len(polyline) // 40)]:
        edge, _, snapped = route_engine.NETWORK.snap(pt[0], pt[1])
        if geo.haversine_m(snapped[0], snapped[1], pt[0], pt[1]) < 40:
            groups.add(edge.closure_group)
    return groups


def test_missed_turn_causes_reroute_from_new_position():
    _recommend()
    r = client.post("/guidance/respond", json={"text": "I missed the turn", "minute": 14.0})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "missed_turn"
    assert body["rerouted"] is True
    assert "re-rout" in body["transcriptText"].lower()
    rec = body["recommendation"]
    assert rec is not None
    best = next(c for c in rec["candidates"] if c["routeId"] == rec["recommendedRouteId"])
    start = best["polyline"][0]
    user = body["userPosition"]
    assert geo.haversine_m(start[0], start[1], user["lon"], user["lat"]) < 250, (
        "re-route must start from the deviated position")


def test_visibility_lost_changes_recommendation():
    """Replays the judge-demo beat: report mid-descent -> route must change."""
    STATE.reset()
    baseline = _recommend(minute=16.0)
    old_best = _route(baseline, baseline["recommendedRouteId"])
    # Drive until just past the second real maneuver (onto the canyon
    # descent), mirroring the judge-demo script's trigger.
    real = [m for m in old_best["maneuvers"] if m["type"] != "depart"]
    target = sum(m["distanceMeters"] for m in real[:2]) + 250.0
    while STATE.user.routeProgressMeters < target:
        client.post("/user/advance", json={"meters": 91.44})
    r = client.post("/guidance/respond",
                    json={"text": "No, I can't see ahead. It's bright orange.",
                          "minute": STATE.user.minute})
    body = r.json()
    assert body["intent"] == "visibility_lost"
    assert body["rerouted"] is True
    assert any(a["type"] == "set_visibility_lost" for a in body["actions"])
    rec = body["recommendation"]
    new_best = next(c for c in rec["candidates"] if c["routeId"] == rec["recommendedRouteId"])
    # The report must visibly change the plan: a U-turn away from the reported
    # zone, or a materially different path geometry.
    turned_around = new_best["maneuvers"][0]["type"] == "uturn"
    length_changed = abs(new_best["totalDistanceMeters"]
                         - (old_best["totalDistanceMeters"] - target)) > 400
    assert turned_around or length_changed, (
        "visibility report must alter the recommended plan")


def test_user_advance_moves_along_route_and_reports_maneuvers():
    _recommend()
    r1 = client.post("/user/advance", json={"meters": 91.44}).json()
    r2 = client.post("/user/advance", json={"meters": 300.0}).json()
    assert r2["position"]["routeProgressMeters"] > r1["position"]["routeProgressMeters"]
    assert r2["remainingDistanceMeters"] < r1["remainingDistanceMeters"]
    assert r2["currentInstruction"]
    assert r2["remainingBufferMinutes"] > 0
