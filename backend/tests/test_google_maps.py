"""Google integration units: polyline codec, step mapping, graceful fallback.

No network, no key required — live calls are exercised via fixtures.
"""

import pytest

from app import google_maps, route_engine
from app.google_maps import GoogleUnavailable, decode_polyline, parse_routes_response


def test_decode_polyline_known_vector():
    # Canonical example from Google's polyline documentation.
    pts = decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@")
    expected = [[-120.2, 38.5], [-120.95, 40.7], [-126.453, 43.252]]
    assert len(pts) == 3
    for got, exp in zip(pts, expected):
        assert got[0] == pytest.approx(exp[0], abs=1e-5)
        assert got[1] == pytest.approx(exp[1], abs=1e-5)


FIXTURE = {
    "routes": [{
        "duration": "540s",
        "distanceMeters": 6100,
        "description": "Sunset Blvd and Chautauqua Blvd",
        "polyline": {"encodedPolyline": "_p~iF~ps|U_ulLnnqC_mqNvxq`@"},
        "legs": [{"steps": [
            {"navigationInstruction": {"maneuver": "DEPART",
                                       "instructions": "Head south on Palisades Dr"},
             "distanceMeters": 2400, "staticDuration": "210s",
             "startLocation": {"latLng": {"latitude": 34.0648, "longitude": -118.5392}}},
            {"navigationInstruction": {"maneuver": "TURN_RIGHT",
                                       "instructions": "Turn right onto W Sunset Blvd"},
             "distanceMeters": 700, "staticDuration": "80s",
             "startLocation": {"latLng": {"latitude": 34.0458, "longitude": -118.5232}}},
            {"navigationInstruction": {"maneuver": "TURN_LEFT",
                                       "instructions": "Turn left onto Chautauqua Blvd"},
             "distanceMeters": 1100, "staticDuration": "140s",
             "startLocation": {"latLng": {"latitude": 34.0385, "longitude": -118.5190}}},
        ]}],
    }],
}


def test_parse_routes_response_maps_steps_to_maneuvers():
    routes = parse_routes_response(FIXTURE, "Santa Monica staging area (demo)")
    assert len(routes) == 1
    r = routes[0]
    assert r["durationMinutes"] == pytest.approx(9.0)
    assert r["distanceMeters"] == 6100
    kinds = [m.type for m in r["maneuvers"]]
    assert kinds == ["depart", "turn_right", "turn_left", "arrive"]
    # Google semantics: distance BEFORE a maneuver = previous step's length.
    assert r["maneuvers"][1].distanceMeters == 2400
    assert r["maneuvers"][2].distanceMeters == 700
    assert "Sunset" in r["maneuvers"][1].roadName
    assert r["maneuvers"][1].coordinate == [-118.5232, 34.0458]
    assert "lower-risk zone" in r["maneuvers"][-1].instruction


def test_compute_routes_without_key_raises_unavailable(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    with pytest.raises(GoogleUnavailable):
        google_maps.compute_routes((-118.54, 34.06), (-118.50, 34.02), "Safe zone")


def test_state_falls_back_to_demo_graph_when_google_unreachable(monkeypatch):
    """With a key set but the API unreachable, recommendation still works."""
    from app.state import STATE

    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-key-not-real")

    def boom(*args, **kwargs):
        raise GoogleUnavailable("offline test")

    monkeypatch.setattr(route_engine, "recommend_routes_google", boom)
    STATE.reset()
    rec = STATE.recommend(minute=16.0)
    assert rec.source == "demo_graph"
    assert rec.candidates, "fallback must still produce candidates"
    assert rec.destination is not None


def test_elevation_grid_bilinear_interpolation():
    grid = google_maps.ElevationGrid(
        west=0.0, south=0.0, east=1.0, north=1.0, cols=2, rows=2,
        heights=[0.0, 100.0, 200.0, 300.0], source="test")
    assert grid.height_at(0.0, 0.0) == pytest.approx(0.0)
    assert grid.height_at(1.0, 0.0) == pytest.approx(100.0, abs=0.5)
    assert grid.height_at(0.0, 1.0) == pytest.approx(200.0, abs=0.5)
    assert grid.height_at(0.5, 0.5) == pytest.approx(150.0, abs=1.0)
