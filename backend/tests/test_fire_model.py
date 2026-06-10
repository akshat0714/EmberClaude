"""Fire model physics sanity checks: wind direction, wind speed, determinism."""

import math

from app import demo_world, fire_model, geo
from app.models import SimulationRequest


def _max_spread_distance(cells, minute, bearing_center, tolerance=45.0):
    """Furthest ignited cell from the ignition point within a bearing sector."""
    ilon, ilat = fire_model.IGNITION_LONLAT
    best = 0.0
    for c in cells:
        if c.ignition > minute:
            continue
        b = geo.bearing_deg(ilon, ilat, c.lon, c.lat)
        if geo.angle_diff_deg(b, bearing_center) <= tolerance:
            best = max(best, geo.haversine_m(ilon, ilat, c.lon, c.lat))
    return best


def test_fire_spreads_more_strongly_downwind():
    params = SimulationRequest()  # wind FROM 12 deg -> blows TOWARD 192 deg
    cells = fire_model.simulate_cells(params, demo_world.fuel_at)
    downwind = _max_spread_distance(cells, 45, bearing_center=192.0)
    upwind = _max_spread_distance(cells, 45, bearing_center=12.0)
    assert downwind > 0 and upwind >= 0
    assert downwind > upwind * 1.8, (
        f"downwind spread {downwind:.0f} m should clearly exceed upwind {upwind:.0f} m")


def test_stronger_wind_increases_spread_distance():
    calm = fire_model.simulate_cells(
        SimulationRequest(windSpeedMph=12), demo_world.fuel_at)
    storm = fire_model.simulate_cells(
        SimulationRequest(windSpeedMph=55), demo_world.fuel_at)
    # Measure early (minute 25), before the front hits the coastline cap.
    d_calm = _max_spread_distance(calm, 25, 192.0)
    d_storm = _max_spread_distance(storm, 25, 192.0)
    assert d_storm > d_calm * 1.15, f"55 mph ({d_storm:.0f} m) vs 12 mph ({d_calm:.0f} m)"
    # And the storm run must have ignited clearly more ground overall.
    burned_calm = len([c for c in calm if c.ignition <= 45])
    burned_storm = len([c for c in storm if c.ignition <= 45])
    assert burned_storm > burned_calm * 1.3, f"{burned_storm} vs {burned_calm} cells by minute 45"


def test_model_is_deterministic():
    a = fire_model.simulate_cells(SimulationRequest(), demo_world.fuel_at)
    b = fire_model.simulate_cells(SimulationRequest(), demo_world.fuel_at)
    assert [(c.key, round(c.ignition, 6)) for c in a] == [(c.key, round(c.ignition, 6)) for c in b]


def test_fire_does_not_burn_the_ocean():
    cells = fire_model.simulate_cells(SimulationRequest(), demo_world.fuel_at)
    for c in cells:
        assert c.lat > geo.coast_lat(c.lon), "ignited cell must stay on land"


def test_simulation_bundle_has_all_layers():
    sim = fire_model.run_simulation(SimulationRequest(), demo_world.fuel_at)
    key = "30"
    assert sim.fireCellsByMinute[key], "active cells expected at minute 30"
    assert key in sim.firePerimeterByMinute
    assert sim.smokeZonesByMinute[key], "smoke plumes expected"
    assert sim.riskZonesByMinute[key], "risk rings expected"
    assert key in sim.uncertaintyEnvelopeByMinute
    perimeter = sim.firePerimeterByMinute[key]
    assert perimeter.areaSqKm > 0.2
    assert not math.isnan(perimeter.areaSqKm)
