"""Palisades Fire 3D Escape Twin — FastAPI backend.

Run locally:  uvicorn app.main:app --reload --port 8000
Static demo data is served under /data/* for the frontend.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import demo_world, guidance
from .models import (
    AdvanceRequest,
    AdvanceResult,
    DeviateRequest,
    GuidanceRequest,
    GuidanceResponse,
    PersonProfile,
    RouteRecommendation,
    RouteRequest,
    ScenarioInfo,
    SimulationRequest,
    SimulationResult,
    UserPosition,
    SAFETY_DISCLAIMER,
)
from .state import STATE

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "demo"

app = FastAPI(
    title="Palisades Fire 3D Escape Twin API",
    description=("Simulation-backed wildfire evacuation decision-support demo. "
                 "All outputs are modeled demo data — follow official evacuation orders."),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local demo only
    allow_methods=["*"],
    allow_headers=["*"],
)

if DATA_DIR.exists():
    app.mount("/data", StaticFiles(directory=str(DATA_DIR)), name="data")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "palisades-escape-twin", "version": "1.0.0",
            "disclaimer": SAFETY_DISCLAIMER}


@app.get("/scenario/palisades-demo", response_model=ScenarioInfo)
def scenario() -> ScenarioInfo:
    datasets = {
        "roads": "/data/palisades_roads.json",
        "buildings": "/data/palisades_buildings.json",
        "vegetation": "/data/palisades_vegetation_zones.json",
        "fireCells": "/data/palisades_fire_cells.json",
        "fireTimeline": "/data/palisades_fire_timeline.json",
        "smokeZones": "/data/palisades_smoke_zones.json",
        "riskZones": "/data/palisades_risk_zones.json",
        "routes": "/data/palisades_routes.json",
        "profiles": "/data/person_profiles.json",
        "safeZones": "/data/shelters_and_safe_zones.json",
        "judgeScript": "/data/judge_demo_script.json",
    }
    return ScenarioInfo(
        name="palisades-demo",
        label="Historical Palisades Fire Replay + Simulated Evacuation",
        center=list(demo_world.SCENE_CENTER),
        bounds=demo_world.SCENE_BOUNDS,
        ignitionPoint=[-118.5421, 34.0708],
        ignitionTimeLocal="2025-01-07T10:30:00-08:00",
        defaults=SimulationRequest(),
        timelineMinutes=[0, 5, 10, 15, 20, 30, 45, 60],
        userStart=list(demo_world.USER_START),
        safeZones=demo_world.SAFE_ZONES,
        datasets=datasets,
        disclaimers=[
            SAFETY_DISCLAIMER,
            "Geometry, buildings and vegetation are synthetic demo data approximating public reports.",
            "Routes are modeled lowest-risk suggestions, never guarantees.",
        ])


@app.get("/profiles", response_model=List[PersonProfile])
def profiles() -> List[PersonProfile]:
    return demo_world.PROFILES


@app.post("/simulation/run", response_model=SimulationResult)
def run_simulation(req: SimulationRequest) -> SimulationResult:
    return STATE.run_simulation(req)


@app.post("/routes/recommend", response_model=RouteRecommendation)
def recommend(req: RouteRequest) -> RouteRecommendation:
    STATE.profile_id = req.profileId
    STATE.conditions.closedRoads = req.conditions.closedRoads
    if req.conditions.visibilityLost and not STATE.conditions.visibilityLost:
        STATE.report_visibility_lost()
    elif not req.conditions.visibilityLost:
        STATE.conditions.visibilityLost = False
        STATE.conditions.smokeSensitivityBoost = req.conditions.smokeSensitivityBoost
        STATE.conditions.reportedBlockNear = req.conditions.reportedBlockNear
    try:
        return STATE.recommend(
            position=(req.position[0], req.position[1]),
            heading=req.headingDeg, minute=req.minute,
            destination_id=req.destinationId)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/guidance/respond", response_model=GuidanceResponse)
def guidance_respond(req: GuidanceRequest) -> GuidanceResponse:
    return guidance.respond(req, STATE)


@app.post("/user/advance", response_model=AdvanceResult)
def user_advance(req: AdvanceRequest) -> AdvanceResult:
    return STATE.advance(req.meters)


@app.post("/user/deviate", response_model=UserPosition)
def user_deviate(req: DeviateRequest) -> UserPosition:
    return STATE.deviate(req.mode)


@app.post("/scenario/reset")
def scenario_reset() -> dict:
    STATE.reset()
    return {"status": "reset", "userStart": list(demo_world.USER_START)}
