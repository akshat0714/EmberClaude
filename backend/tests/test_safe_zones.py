"""Dynamic safe-zone behavior: selection, encroachment, relocation + re-route."""

from fastapi.testclient import TestClient

from app import demo_world, safe_zones
from app.main import app
from app.state import STATE

client = TestClient(app)


def test_zone_statuses_degrade_as_fire_approaches():
    early = {s.zone.id: s for s in STATE.zone_statuses(5.0)}
    late = {s.zone.id: s for s in STATE.zone_statuses(70.0)}
    order = {"safe": 0, "at_risk": 1, "compromised": 2}
    for zid in early:
        assert order[late[zid].status] >= order[early[zid].status], (
            f"{zid} cannot get SAFER as the fire spreads")
    # The coastal lot sits downwind: it must eventually be compromised.
    assert late["will_rogers_beach_lot"].status == "compromised"
    # Westwood is far inland-east: still viable at minute 70.
    assert late["westwood_rec_center"].status != "compromised"


def test_select_destination_prefers_nearest_viable():
    statuses = STATE.zone_statuses(10.0)
    chosen = safe_zones.select_destination(statuses, demo_world.USER_START)
    viable = [s for s in statuses if s.status != "compromised"]
    nearest = min(viable, key=lambda s: __import__("app.geo", fromlist=["x"]).haversine_m(
        demo_world.USER_START[0], demo_world.USER_START[1], s.zone.lon, s.zone.lat))
    assert chosen.zone.id == nearest.zone.id


def test_select_destination_never_returns_nothing_when_all_compromised():
    statuses = STATE.zone_statuses(10.0)
    for s in statuses:
        s.status = "compromised"
    chosen = safe_zones.select_destination(statuses, demo_world.USER_START)
    assert chosen is not None  # least-bad zone still offered


def test_predicted_zone_encroachment_moves_safe_zone_and_reroutes():
    """The user's core ask: when the predicted zone encompasses the active
    safe zone, the destination MOVES and the route re-plans mid-drive."""
    STATE.reset()
    rec = STATE.recommend(minute=16.0)
    first_dest = rec.destination
    assert first_dest is not None

    changed = None
    for _ in range(400):
        r = STATE.advance(140.0)
        if r.safeZoneChanged:
            changed = r
            break
        if r.arrived:
            # Arrived before encroachment: jump time forward while parked —
            # the watcher must still relocate when the prediction reaches it.
            STATE.user.minute += 6.0
    assert changed is not None, "predicted-zone encroachment must trigger relocation"
    assert changed.destination is not None
    assert changed.destination.id != first_dest.id
    assert "predicted spread zone" in changed.safeZoneNote
    assert "Redirecting" in changed.safeZoneNote
    assert changed.recommendation is not None, "relocation must carry a fresh route"
    new_best = next(c for c in changed.recommendation.candidates
                    if c.routeId == changed.recommendation.recommendedRouteId)
    end = new_best.polyline[-1]
    assert abs(end[0] - changed.destination.lon) < 0.01
    assert abs(end[1] - changed.destination.lat) < 0.01


def test_safezones_endpoint_reports_statuses():
    STATE.reset()
    body = client.get("/safezones", params={"minute": 40}).json()
    assert len(body["statuses"]) == len(demo_world.SAFE_ZONES)
    for s in body["statuses"]:
        assert s["status"] in ("safe", "at_risk", "compromised")
        assert "bufferMinutes" in s
    assert "official" in body["disclaimer"].lower()
