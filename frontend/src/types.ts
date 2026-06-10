/** Shared API types mirroring the backend Pydantic models. */

export type LonLat = [number, number];

export interface FireCell {
  id: string;
  lat: number;
  lon: number;
  radiusMeters: number;
  ignitionMinute: number;
  intensity: number;
  confidence: number;
  source: "historical_demo" | "predicted" | "observed";
  fuelLoad: number;
  slopeFactor: number;
  windAlignment: number;
  spreadRateMetersPerMinute: number;
}

export interface SmokeZone {
  id: string;
  minute: number;
  densityLevel: "light" | "moderate" | "heavy";
  density: number;
  polygon: LonLat[];
  centerline: LonLat[];
  plumeHeightMeters: number;
}

export interface RiskZone {
  id: string;
  minute: number;
  level: "extreme" | "high" | "elevated";
  riskScore: number;
  polygon: LonLat[];
  label: string;
  guidance: string;
}

export interface FirePerimeter {
  minute: number;
  polygon: LonLat[];
  areaSqKm: number;
  source: "replay_model" | "predicted";
  confidence: number;
}

export interface UncertaintyEnvelope {
  minute: number;
  polygon: LonLat[];
  bufferMeters: number;
  note: string;
}

export interface SimulationParams {
  windSpeedMph: number;
  windFromDeg: number;
  fireIntensity: number;
  nowMinute: number;
  horizonMinutes: number;
}

export interface SimulationResult {
  params: SimulationParams;
  minutes: number[];
  ignitionPoint: LonLat;
  fireCellsByMinute: Record<string, FireCell[]>;
  predictedFireCellsByMinute: Record<string, FireCell[]>;
  firePerimeterByMinute: Record<string, FirePerimeter>;
  riskZonesByMinute: Record<string, RiskZone[]>;
  smokeZonesByMinute: Record<string, SmokeZone[]>;
  uncertaintyEnvelopeByMinute: Record<string, UncertaintyEnvelope>;
  modelNotes: string[];
  disclaimer: string;
}

export interface Maneuver {
  id: string;
  type: string;
  instruction: string;
  roadName: string;
  distanceMeters: number;
  expectedTimeSeconds: number;
  coordinate: LonLat;
  hazardReason?: string | null;
}

export interface RouteScore {
  fireBufferScore: number;
  smokeAvoidanceScore: number;
  travelTimeScore: number;
  roadClosureComplianceScore: number;
  profileSuitabilityScore: number;
  congestionScore: number;
  backupRouteScore: number;
  final: number;
}

export interface CandidateRoute {
  routeId: string;
  name: string;
  routeType: "fastest" | "lowest_smoke" | "max_fire_buffer" | "reroute";
  polyline: LonLat[];
  maneuvers: Maneuver[];
  totalDistanceMeters: number;
  estimatedTravelTimeMinutes: number;
  fireArrivalBufferMinutes: number;
  smokeExposureScore: number;
  congestionRisk: number;
  roadClosureRisk: number;
  accessibilityScore: number;
  confidence: number;
  warnings: string[];
  score?: RouteScore | null;
}

export interface RouteRecommendation {
  recommendedRouteId: string;
  candidates: CandidateRoute[];
  explanation: string;
  whyNotFastest: string;
  safetyReminder: string;
  generatedAtMinute: number;
}

export interface UserPosition {
  lon: number;
  lat: number;
  headingDeg: number;
  minute: number;
  routeId?: string | null;
  routeProgressMeters: number;
  onRoute: boolean;
  status: "idle" | "enroute" | "off_route" | "arrived";
}

export interface AdvanceResult {
  position: UserPosition;
  currentInstruction: string;
  nextManeuver?: Maneuver | null;
  distanceToManeuverMeters: number;
  remainingDistanceMeters: number;
  remainingBufferMinutes: number;
  smokeDensityHere: number;
  arrived: boolean;
}

export interface GuidanceAction {
  type: string;
  detail: string;
}

export interface GuidanceResponse {
  intent: string;
  transcriptText: string;
  speechText: string;
  actions: GuidanceAction[];
  rerouted: boolean;
  recommendation?: RouteRecommendation | null;
  userPosition?: UserPosition | null;
  safetyReminder: string;
}

export interface PersonProfile {
  id: string;
  name: string;
  description: string;
  travelSpeedMph: number;
  smokeSensitivity: number;
  mobilityScore: number;
  prefersFewerTurns: boolean;
}

export interface SafeZone {
  id: string;
  name: string;
  lon: number;
  lat: number;
  kind: string;
  notes: string;
}

export interface ScenarioInfo {
  name: string;
  label: string;
  center: LonLat;
  bounds: [number, number, number, number];
  ignitionPoint: LonLat;
  ignitionTimeLocal: string;
  defaults: SimulationParams;
  timelineMinutes: number[];
  userStart: LonLat;
  safeZones: SafeZone[];
  datasets: Record<string, string>;
  disclaimers: string[];
}

export interface JudgeStep {
  id: string;
  action: string;
  caption?: string;
  voice?: string;
  userLine?: string;
  durationMs: number;
  params?: Record<string, number>;
}

export interface JudgeScript {
  title: string;
  steps: JudgeStep[];
}

export interface GeoFeature {
  type: "Feature";
  properties: Record<string, unknown>;
  geometry: { type: string; coordinates: unknown };
}

export interface GeoCollection {
  type: "FeatureCollection";
  properties?: Record<string, unknown>;
  features: GeoFeature[];
}

export interface TranscriptMsg {
  id: number;
  who: "user" | "assistant" | "system";
  text: string;
  at: string;
}
