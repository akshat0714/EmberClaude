"""Pydantic models shared by the simulation, routing and guidance engines.

Coordinate convention everywhere: [lon, lat] pairs (GeoJSON order).
All hazard numbers are MODELED values from a demo scenario — the API
attaches disclaimers and the guidance layer never presents them as
guarantees.
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

LonLat = List[float]  # [lon, lat]

SAFETY_DISCLAIMER = (
    "Simulation only — modeled guidance from demo scenario inputs. "
    "Follow official evacuation orders and emergency personnel. Avoid closed roads."
)


class FireCell(BaseModel):
    id: str
    lat: float
    lon: float
    radiusMeters: float
    ignitionMinute: float
    intensity: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    source: Literal["historical_demo", "predicted", "observed"]
    fuelLoad: float
    slopeFactor: float
    windAlignment: float
    spreadRateMetersPerMinute: float


class SmokeZone(BaseModel):
    id: str
    minute: int
    densityLevel: Literal["light", "moderate", "heavy"]
    density: float = Field(ge=0.0, le=1.0)
    polygon: List[LonLat]
    centerline: List[LonLat]
    plumeHeightMeters: float
    source: str = "plume_model_demo"


class RiskZone(BaseModel):
    id: str
    minute: int
    level: Literal["extreme", "high", "elevated"]
    riskScore: float = Field(ge=0.0, le=1.0)
    polygon: List[LonLat]
    label: str
    guidance: str


class FirePerimeter(BaseModel):
    minute: int
    polygon: List[LonLat]
    areaSqKm: float
    source: Literal["replay_model", "predicted"]
    confidence: float


class UncertaintyEnvelope(BaseModel):
    minute: int
    polygon: List[LonLat]
    bufferMeters: float
    note: str = "Dotted envelope: spread beyond the predicted perimeter is plausible."


class PersonProfile(BaseModel):
    id: str
    name: str
    description: str
    travelSpeedMph: float
    smokeSensitivity: float = Field(ge=0.0, le=1.0)
    mobilityScore: float = Field(ge=0.0, le=1.0)
    prefersFewerTurns: bool = False


class UserPosition(BaseModel):
    lon: float
    lat: float
    headingDeg: float = 0.0
    minute: float = 0.0
    routeId: Optional[str] = None
    routeProgressMeters: float = 0.0
    onRoute: bool = True
    status: Literal["idle", "enroute", "off_route", "arrived"] = "idle"


class Maneuver(BaseModel):
    id: str
    type: Literal[
        "depart", "continue", "turn_left", "turn_right",
        "slight_left", "slight_right", "uturn", "merge", "arrive",
    ]
    instruction: str
    roadName: str
    distanceMeters: float
    expectedTimeSeconds: float
    coordinate: LonLat
    hazardReason: Optional[str] = None


class RouteScore(BaseModel):
    fireBufferScore: float
    smokeAvoidanceScore: float
    travelTimeScore: float
    roadClosureComplianceScore: float
    profileSuitabilityScore: float
    congestionScore: float
    backupRouteScore: float
    final: float


class CandidateRoute(BaseModel):
    routeId: str
    name: str
    routeType: Literal["fastest", "lowest_smoke", "max_fire_buffer", "reroute"]
    polyline: List[LonLat]
    maneuvers: List[Maneuver]
    totalDistanceMeters: float
    estimatedTravelTimeMinutes: float
    fireArrivalBufferMinutes: float
    smokeExposureScore: float  # 0 (clear) .. 100 (worst modeled exposure)
    congestionRisk: float = Field(ge=0.0, le=1.0)
    roadClosureRisk: float = Field(ge=0.0, le=1.0)
    accessibilityScore: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    warnings: List[str] = []
    score: Optional[RouteScore] = None


class RouteRecommendation(BaseModel):
    recommendedRouteId: str
    candidates: List[CandidateRoute]
    explanation: str
    whyNotFastest: str
    safetyReminder: str = SAFETY_DISCLAIMER
    generatedAtMinute: float


class SimulationRequest(BaseModel):
    windSpeedMph: float = 38.0
    windFromDeg: float = 12.0  # Santa Ana event: wind FROM the NNE
    fireIntensity: float = Field(default=0.85, ge=0.1, le=1.0)
    nowMinute: float = 0.0
    horizonMinutes: float = 75.0


class SimulationResult(BaseModel):
    params: SimulationRequest
    minutes: List[int]
    ignitionPoint: LonLat
    fireCellsByMinute: Dict[str, List[FireCell]]
    predictedFireCellsByMinute: Dict[str, List[FireCell]]
    firePerimeterByMinute: Dict[str, FirePerimeter]
    riskZonesByMinute: Dict[str, List[RiskZone]]
    smokeZonesByMinute: Dict[str, List[SmokeZone]]
    uncertaintyEnvelopeByMinute: Dict[str, UncertaintyEnvelope]
    modelNotes: List[str]
    disclaimer: str = SAFETY_DISCLAIMER


class RouteConditions(BaseModel):
    visibilityLost: bool = False
    closedRoads: List[str] = []
    reportedBlockNear: Optional[LonLat] = None
    smokeSensitivityBoost: float = 0.0


class RouteRequest(BaseModel):
    position: LonLat
    headingDeg: float = 180.0
    minute: float = 0.0
    profileId: str = "standard_adult"
    destinationId: str = "santa_monica_staging"
    conditions: RouteConditions = RouteConditions()


class GuidanceRequest(BaseModel):
    text: str
    minute: float = 0.0
    position: Optional[LonLat] = None
    sessionId: str = "demo"


class GuidanceAction(BaseModel):
    type: Literal["reroute", "speak", "set_visibility_lost", "close_road",
                  "deviate_user", "none", "arrived"]
    detail: str = ""


class GuidanceResponse(BaseModel):
    intent: str
    transcriptText: str
    speechText: str
    actions: List[GuidanceAction] = []
    rerouted: bool = False
    recommendation: Optional[RouteRecommendation] = None
    userPosition: Optional[UserPosition] = None
    safetyReminder: str = SAFETY_DISCLAIMER


class AdvanceRequest(BaseModel):
    meters: float = 91.44  # 300 ft


class DeviateRequest(BaseModel):
    mode: Literal["missed_turn", "off_route", "blocked"] = "missed_turn"


class AdvanceResult(BaseModel):
    position: UserPosition
    currentInstruction: str
    nextManeuver: Optional[Maneuver] = None
    distanceToManeuverMeters: float = 0.0
    remainingDistanceMeters: float = 0.0
    remainingBufferMinutes: float = 0.0
    smokeDensityHere: float = 0.0
    arrived: bool = False


class SafeZone(BaseModel):
    id: str
    name: str
    lon: float
    lat: float
    kind: str
    notes: str


class ScenarioInfo(BaseModel):
    name: str
    label: str
    center: LonLat
    bounds: List[float]  # [west, south, east, north]
    ignitionPoint: LonLat
    ignitionTimeLocal: str
    defaults: SimulationRequest
    timelineMinutes: List[int]
    userStart: LonLat
    safeZones: List[SafeZone]
    datasets: Dict[str, str]
    disclaimers: List[str]
