"""Generate every data/demo/*.json artifact from the deterministic models.

Run from backend/:  python -m scripts.generate_demo_data
Re-running always produces identical files (no wall-clock, no RNG state).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import demo_world, fire_model, route_engine  # noqa: E402
from app.models import SimulationRequest, SAFETY_DISCLAIMER  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "data" / "demo"

DISCLAIMER = ("SYNTHETIC DEMO DATA approximating publicly reported aspects of the "
              "Jan 7, 2025 Palisades Fire. Not official. Not survey accurate. "
              "Never use for real navigation. " + SAFETY_DISCLAIMER)


def dump(name: str, payload: dict | list) -> None:
    path = OUT / name
    path.write_text(json.dumps(payload, indent=1))
    print(f"  wrote {path.relative_to(OUT.parents[1])} ({path.stat().st_size // 1024} KB)")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    params = SimulationRequest()
    print("Simulating baseline Palisades replay ...")
    sim = fire_model.run_simulation(params, demo_world.fuel_at)
    cells = fire_model.simulate_cells(params, demo_world.fuel_at)

    dump("palisades_fire_cells.json", {
        "disclaimer": DISCLAIMER,
        "ignitionPoint": list(fire_model.IGNITION_LONLAT),
        "cells": [fire_model._to_fire_cell(c, c.ignition + 3, "historical_demo", 0).model_dump()
                  for c in cells],
    })
    dump("palisades_fire_timeline.json", {
        "disclaimer": DISCLAIMER,
        "minutes": sim.minutes,
        "fireCellsByMinute": {k: [c.model_dump() for c in v] for k, v in sim.fireCellsByMinute.items()},
        "predictedFireCellsByMinute": {k: [c.model_dump() for c in v]
                                       for k, v in sim.predictedFireCellsByMinute.items()},
        "firePerimeterByMinute": {k: v.model_dump() for k, v in sim.firePerimeterByMinute.items()},
        "uncertaintyEnvelopeByMinute": {k: v.model_dump()
                                        for k, v in sim.uncertaintyEnvelopeByMinute.items()},
        "modelNotes": sim.modelNotes,
    })
    dump("palisades_smoke_zones.json", {
        "disclaimer": DISCLAIMER,
        "smokeZonesByMinute": {k: [z.model_dump() for z in v]
                               for k, v in sim.smokeZonesByMinute.items()},
    })
    dump("palisades_risk_zones.json", {
        "disclaimer": DISCLAIMER,
        "riskZonesByMinute": {k: [z.model_dump() for z in v]
                              for k, v in sim.riskZonesByMinute.items()},
    })

    print("Planning baseline candidate routes ...")
    ctx = route_engine.HazardContext(
        fire_arrival=lambda lon, lat: fire_model.fire_arrival_minute(
            cells, lon, lat, params, fuel_at=demo_world.fuel_at),
        smoke_density=lambda lon, lat, minute: fire_model.smoke_density_at(
            sim.smokeZonesByMinute.get(str(max((m for m in sim.minutes if m <= minute), default=0)), []),
            lon, lat))
    rec = route_engine.recommend_routes(
        demo_world.USER_START, 160.0, 16.0, demo_world.PROFILES[0], ctx)
    dump("palisades_routes.json", {
        "disclaimer": DISCLAIMER,
        "generatedAtMinute": 16.0,
        "recommendation": rec.model_dump(),
    })

    dump("palisades_roads.json", demo_world.generate_roads())
    dump("palisades_buildings.json", demo_world.generate_buildings())
    dump("palisades_vegetation_zones.json", demo_world.generate_vegetation())
    dump("person_profiles.json", {
        "disclaimer": DISCLAIMER,
        "profiles": [p.model_dump() for p in demo_world.PROFILES],
    })
    dump("shelters_and_safe_zones.json", {
        "disclaimer": DISCLAIMER,
        "safeZones": [z.model_dump() for z in demo_world.SAFE_ZONES],
    })

    dump("judge_demo_script.json", {
        "disclaimer": DISCLAIMER,
        "title": "Palisades Fire 3D Escape Twin — Judge Demo",
        "steps": [
            {"id": "intro", "action": "flyOverview", "durationMs": 9000,
             "caption": "Historical replay — Palisades Fire, Jan 7 2025, ~10:30 AM PST. Synthetic demo data.",
             "voice": ("This is a simulation-backed replay of the January seventh Palisades Fire "
                       "with one simulated resident. In any real emergency, follow official "
                       "evacuation orders.")},
            {"id": "ignite", "action": "startReplay", "params": {"minute": 0, "speed": 5},
             "durationMs": 7000,
             "caption": "Minute 0 — ignition modeled on the ridge above Piedra Morada Drive.",
             "voice": "Minute zero. Fire cells detected on the ridge above Palisades Highlands."},
            {"id": "spread", "action": "advanceReplay", "params": {"toMinute": 16}, "durationMs": 14000,
             "caption": "NNE Santa Ana winds ~38 mph drive the front toward the Highlands; smoke pushes downwind.",
             "voice": ("Sustained northeast winds are driving rapid spread toward Palisades Highlands. "
                       "Smoke is drifting downwind across the Temescal corridor.")},
            {"id": "placeUser", "action": "placeUser", "durationMs": 7000,
             "caption": "Simulated resident on Palisades Drive — inside the 30-minute modeled spread envelope.",
             "voice": ("A simulated resident is in the Highlands, inside the thirty minute "
                       "modeled spread envelope.")},
            {"id": "ask", "action": "userAsks", "userLine": "Where do I go?", "durationMs": 14000,
             "caption": "The resident asks for guidance."},
            {"id": "compare", "action": "showComparison", "durationMs": 9000,
             "caption": "Three candidates scored: fastest / lowest smoke / largest fire buffer."},
            {"id": "select", "action": "selectRecommended", "durationMs": 8000,
             "caption": "Candidates scored — highest FinalRouteScore selected.",
             "voice": ""},
            {"id": "drive1", "action": "driveUntilProgress",
             "params": {"pastManeuvers": 2, "plusMeters": 250},
             "durationMs": 0, "caption": "Turn-by-turn guidance while the fire keeps spreading."},
            {"id": "visibility", "action": "userAsks",
             "userLine": "No, I can't see ahead. It's bright orange.", "durationMs": 15000,
             "caption": "Live report: visibility lost — smoke hazard re-weighted, route recalculated."},
            {"id": "reroute", "action": "highlightReroute", "durationMs": 7000,
             "caption": "The blue path changes: the smoke-heavy descent is avoided."},
            {"id": "drive2", "action": "driveUntilArrived", "durationMs": 0,
             "caption": "Continuing on the updated route toward the nearest staging area."},
            {"id": "arriveStaging", "action": "arrive", "durationMs": 7000,
             "caption": "First staging area reached — the model keeps watching the prediction.",
             "voice": ("You have reached the staging area. I am monitoring the modeled spread "
                       "prediction from here. Stand by and follow official instructions.")},
            {"id": "watchRelocation", "action": "holdForRelocation",
             "params": {"timeoutMs": 45000, "speed": 8}, "durationMs": 0,
             "caption": "The predicted spread zone keeps growing toward the coast…"},
            {"id": "drive3", "action": "driveUntilArrived", "durationMs": 0,
             "caption": "Safe zone MOVED — driving the new route away from the predicted zone."},
            {"id": "arriveFinal", "action": "arrive", "durationMs": 8000,
             "caption": "Simulated lower-risk zone reached.",
             "voice": ("You have reached the simulated lower-risk zone. Continue to follow "
                       "official emergency guidance.")},
            {"id": "summary", "action": "showSummary", "durationMs": 0,
             "caption": "Demo complete — fire predicted, safe zone relocated, guardrails preserved."},
        ],
    })
    print("Done.")


if __name__ == "__main__":
    main()
