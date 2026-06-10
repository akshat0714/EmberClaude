/** Thin typed client for the FastAPI backend. */

import type {
  AdvanceResult,
  GeoCollection,
  GuidanceResponse,
  JudgeScript,
  PersonProfile,
  RouteRecommendation,
  ScenarioInfo,
  SimulationParams,
  SimulationResult,
  UserPosition,
} from "../types";

const BASE = (import.meta.env?.VITE_API_BASE as string | undefined) ?? "http://127.0.0.1:8000";

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`${init?.method ?? "GET"} ${path} -> ${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => http<{ status: string }>("/health"),
  scenario: () => http<ScenarioInfo>("/scenario/palisades-demo"),
  profiles: () => http<PersonProfile[]>("/profiles"),
  dataset: <T = GeoCollection>(path: string) => http<T>(path),
  judgeScript: (path: string) => http<JudgeScript & { disclaimer: string }>(path),

  runSimulation: (params: Partial<SimulationParams>) =>
    http<SimulationResult>("/simulation/run", { method: "POST", body: JSON.stringify(params) }),

  recommendRoutes: (body: {
    position: [number, number];
    headingDeg?: number;
    minute?: number;
    profileId?: string;
    destinationId?: string;
    conditions?: {
      visibilityLost?: boolean;
      closedRoads?: string[];
      smokeSensitivityBoost?: number;
    };
  }) => http<RouteRecommendation>("/routes/recommend", { method: "POST", body: JSON.stringify(body) }),

  guidance: (body: { text: string; minute: number; position?: [number, number] }) =>
    http<GuidanceResponse>("/guidance/respond", { method: "POST", body: JSON.stringify(body) }),

  advance: (meters: number) =>
    http<AdvanceResult>("/user/advance", { method: "POST", body: JSON.stringify({ meters }) }),

  deviate: (mode: "missed_turn" | "off_route" | "blocked") =>
    http<UserPosition>("/user/deviate", { method: "POST", body: JSON.stringify({ mode }) }),

  reset: () => http<{ status: string }>("/scenario/reset", { method: "POST", body: "{}" }),
};

export type ApiClient = typeof api;
