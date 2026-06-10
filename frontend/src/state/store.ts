/** Central app state: scenario, simulation frames, user, routes, assistant. */

import { create } from "zustand";
import { api } from "../api/client";
import { speak } from "../lib/speech";
import type {
  AdvanceResult,
  CandidateRoute,
  GeoCollection,
  GuidanceResponse,
  JudgeScript,
  LonLat,
  PersonProfile,
  RouteRecommendation,
  ScenarioInfo,
  SimulationResult,
  TranscriptMsg,
  UserPosition,
} from "../types";

export interface LayerToggles {
  buildings: boolean;
  vegetation: boolean;
  smoke: boolean;
  risk: boolean;
  uncertainty: boolean;
  predicted: boolean;
  labels: boolean;
}

export interface JudgeState {
  running: boolean;
  stepIndex: number;
  caption: string;
  summary: string[] | null;
}

export interface StatusMetrics {
  instruction: string;
  nextManeuver: string;
  distanceToManeuverM: number;
  remainingM: number;
  bufferMin: number;
  smokeHere: number;
  arrived: boolean;
}

interface Datasets {
  roads?: GeoCollection;
  buildings?: GeoCollection;
  vegetation?: GeoCollection;
  judgeScript?: JudgeScript;
}

let msgId = 0;
const now = () => new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export interface AppState {
  bootError: string | null;
  loading: boolean;
  loadingStage: string;
  scenario: ScenarioInfo | null;
  datasets: Datasets;
  profiles: PersonProfile[];
  profileId: string;
  sim: SimulationResult | null;
  simParams: { windSpeedMph: number; windFromDeg: number; fireIntensity: number };
  simMinute: number;
  playing: boolean;
  playbackSpeed: number;
  layers: LayerToggles;
  closures: string[];
  visibilityLost: boolean;
  reportedZone: { center: LonLat; radiusM: number } | null;
  user: UserPosition | null;
  driving: boolean;
  recommendation: RouteRecommendation | null;
  activeRouteId: string | null;
  status: StatusMetrics;
  transcript: TranscriptMsg[];
  assistantBusy: boolean;
  muted: boolean;
  followCam: boolean;
  judge: JudgeState;
  toast: string | null;

  boot: () => Promise<void>;
  setLoadingStage: (s: string) => void;
  setSimParam: (k: "windSpeedMph" | "windFromDeg" | "fireIntensity", v: number) => Promise<void>;
  rerunSimulation: () => Promise<void>;
  setMinute: (m: number) => void;
  setPlaying: (p: boolean) => void;
  setPlaybackSpeed: (s: number) => void;
  toggleLayer: (k: keyof LayerToggles) => void;
  toggleClosure: (group: string) => Promise<void>;
  setProfile: (id: string) => void;
  placeUser: () => void;
  askGuidance: (text: string, opts?: { silentVoice?: boolean }) => Promise<GuidanceResponse | null>;
  applyAdvance: (r: AdvanceResult) => void;
  advanceUser: (meters: number) => Promise<AdvanceResult | null>;
  simulateMissedTurn: () => Promise<void>;
  simulateBlockedRoad: () => Promise<void>;
  simulateVisibilityLost: () => Promise<void>;
  setActiveRoute: (id: string) => void;
  setDriving: (d: boolean) => void;
  setFollowCam: (f: boolean) => void;
  setMutedState: (m: boolean) => void;
  pushTranscript: (who: TranscriptMsg["who"], text: string) => void;
  setJudge: (j: Partial<JudgeState>) => void;
  setToast: (t: string | null) => void;
  resetScenario: () => Promise<void>;
  exportScenario: () => void;
}

export const useApp = create<AppState>((set, get) => ({
  bootError: null,
  loading: true,
  loadingStage: "Contacting simulation backend…",
  scenario: null,
  datasets: {},
  profiles: [],
  profileId: "standard_adult",
  sim: null,
  simParams: { windSpeedMph: 38, windFromDeg: 12, fireIntensity: 0.85 },
  simMinute: 0,
  playing: false,
  playbackSpeed: 2,
  layers: {
    buildings: true,
    vegetation: true,
    smoke: true,
    risk: true,
    uncertainty: true,
    predicted: true,
    labels: true,
  },
  closures: [],
  visibilityLost: false,
  reportedZone: null,
  user: null,
  driving: false,
  recommendation: null,
  activeRouteId: null,
  status: {
    instruction: "Awaiting scenario start.",
    nextManeuver: "—",
    distanceToManeuverM: 0,
    remainingM: 0,
    bufferMin: 0,
    smokeHere: 0,
    arrived: false,
  },
  transcript: [],
  assistantBusy: false,
  muted: false,
  followCam: false,
  judge: { running: false, stepIndex: -1, caption: "", summary: null },
  toast: null,

  setLoadingStage: (s) => set({ loadingStage: s }),

  boot: async () => {
    try {
      set({ loadingStage: "Contacting simulation backend…" });
      await api.health();
      set({ loadingStage: "Loading Palisades scenario…" });
      const scenario = await api.scenario();
      const profiles = await api.profiles();
      set({ scenario, profiles, loadingStage: "Loading demo world (roads · buildings · fuel)…" });
      const [roads, buildings, vegetation, judgeScript] = await Promise.all([
        api.dataset(scenario.datasets.roads),
        api.dataset(scenario.datasets.buildings),
        api.dataset(scenario.datasets.vegetation),
        api.judgeScript(scenario.datasets.judgeScript),
      ]);
      set({
        datasets: { roads, buildings, vegetation, judgeScript },
        loadingStage: "Running fire spread simulation…",
      });
      await api.reset();
      const sim = await api.runSimulation({});
      set({ sim, loadingStage: "Composing 3D scene…" });
    } catch (e) {
      set({
        bootError:
          `${e instanceof Error ? e.message : String(e)} — is the backend running? ` +
          "Start it with: cd backend && .venv/bin/uvicorn app.main:app --port 8000",
        loading: false,
      });
    }
  },

  setSimParam: async (k, v) => {
    set((s) => ({ simParams: { ...s.simParams, [k]: v } }));
    await get().rerunSimulation();
  },

  rerunSimulation: async () => {
    const { simParams } = get();
    const sim = await api.runSimulation(simParams);
    set({ sim });
  },

  setMinute: (m) => set({ simMinute: Math.max(0, Math.min(75, m)) }),
  setPlaying: (p) => set({ playing: p }),
  setPlaybackSpeed: (s) => set({ playbackSpeed: s }),
  toggleLayer: (k) => set((s) => ({ layers: { ...s.layers, [k]: !s.layers[k] } })),

  toggleClosure: async (group) => {
    const closures = get().closures.includes(group)
      ? get().closures.filter((g) => g !== group)
      : [...get().closures, group];
    set({ closures });
    const { user } = get();
    if (user && get().activeRouteId) {
      const rec = await api.recommendRoutes({
        position: [user.lon, user.lat],
        headingDeg: user.headingDeg,
        minute: get().simMinute,
        profileId: get().profileId,
        conditions: { closedRoads: closures, visibilityLost: get().visibilityLost },
      });
      set({ recommendation: rec, activeRouteId: rec.recommendedRouteId });
      get().setToast("Routes recomputed for closure change");
    }
  },

  setProfile: (id) => set({ profileId: id }),

  placeUser: () => {
    const s = get().scenario;
    if (!s) return;
    set({
      user: {
        lon: s.userStart[0],
        lat: s.userStart[1],
        headingDeg: 160,
        minute: get().simMinute,
        routeProgressMeters: 0,
        onRoute: true,
        status: "idle",
      },
    });
  },

  pushTranscript: (who, text) =>
    set((s) => ({ transcript: [...s.transcript, { id: ++msgId, who, text, at: now() }] })),

  askGuidance: async (text, opts) => {
    const { user, simMinute, pushTranscript } = get();
    pushTranscript("user", text);
    set({ assistantBusy: true });
    try {
      const resp = await api.guidance({
        text,
        minute: simMinute,
        position: user ? [user.lon, user.lat] : undefined,
      });
      pushTranscript("assistant", resp.transcriptText);
      if (resp.recommendation) {
        const rec = resp.recommendation;
        const best = rec.candidates.find((c) => c.routeId === rec.recommendedRouteId);
        set((s) => ({
          recommendation: rec,
          activeRouteId: rec.recommendedRouteId,
          status: best
            ? {
                ...s.status,
                instruction: best.maneuvers[0]?.instruction ?? s.status.instruction,
                nextManeuver: best.maneuvers[1]?.instruction ?? "—",
                distanceToManeuverM: best.maneuvers[1]?.distanceMeters ?? 0,
                remainingM: best.totalDistanceMeters,
                bufferMin: best.fireArrivalBufferMinutes,
                arrived: false,
              }
            : s.status,
        }));
      }
      if (resp.userPosition) set({ user: resp.userPosition });
      for (const a of resp.actions) {
        if (a.type === "set_visibility_lost") {
          let zone: { center: LonLat; radiusM: number } | null = null;
          try {
            const parsed = JSON.parse(a.detail) as { center: LonLat; radiusM: number };
            zone = { center: parsed.center, radiusM: parsed.radiusM };
          } catch {
            zone = null;
          }
          set({ visibilityLost: true, reportedZone: zone });
        }
        if (a.type === "reroute") set({ toast: "Re-routing based on current conditions" });
      }
      if (!opts?.silentVoice && !get().muted) void speak(resp.speechText, { interrupt: true });
      return resp;
    } catch (e) {
      pushTranscript("system", `Guidance error: ${e instanceof Error ? e.message : e}`);
      return null;
    } finally {
      set({ assistantBusy: false });
    }
  },

  applyAdvance: (r) => {
    set({
      user: r.position,
      status: {
        instruction: r.currentInstruction,
        nextManeuver: r.nextManeuver?.instruction ?? (r.arrived ? "Arrived" : "—"),
        distanceToManeuverM: r.distanceToManeuverMeters,
        remainingM: r.remainingDistanceMeters,
        bufferMin: r.remainingBufferMinutes,
        smokeHere: r.smokeDensityHere,
        arrived: r.arrived,
      },
    });
    if (r.arrived) set({ driving: false });
  },

  advanceUser: async (meters) => {
    try {
      const r = await api.advance(meters);
      get().applyAdvance(r);
      return r;
    } catch {
      return null;
    }
  },

  simulateMissedTurn: async () => {
    await api.deviate("missed_turn");
    get().setToast("User overshot the turn — deviation detected");
    await get().askGuidance("I missed the turn.");
  },

  simulateBlockedRoad: async () => {
    await get().askGuidance("The road looks blocked.");
  },

  simulateVisibilityLost: async () => {
    await get().askGuidance("No, I can't see ahead. It's bright orange.");
  },

  setActiveRoute: (id) => {
    set({ activeRouteId: id });
    const rec = get().recommendation;
    const route = rec?.candidates.find((c: CandidateRoute) => c.routeId === id);
    if (route) get().setToast(`Active route: ${route.name}`);
  },

  setDriving: (d) => set({ driving: d }),
  setFollowCam: (f) => set({ followCam: f }),
  setMutedState: (m) => set({ muted: m }),
  setJudge: (j) => set((s) => ({ judge: { ...s.judge, ...j } })),
  setToast: (t) => {
    set({ toast: t });
    if (t) window.setTimeout(() => set((s) => (s.toast === t ? { toast: null } : {})), 4200);
  },

  resetScenario: async () => {
    await api.reset();
    const sim = await api.runSimulation(get().simParams);
    set({
      sim,
      simMinute: 0,
      playing: false,
      driving: false,
      user: null,
      recommendation: null,
      activeRouteId: null,
      visibilityLost: false,
      reportedZone: null,
      closures: [],
      transcript: [],
      judge: { running: false, stepIndex: -1, caption: "", summary: null },
      status: {
        instruction: "Awaiting scenario start.",
        nextManeuver: "—",
        distanceToManeuverM: 0,
        remainingM: 0,
        bufferMin: 0,
        smokeHere: 0,
        arrived: false,
      },
    });
  },

  exportScenario: () => {
    const { simParams, simMinute, recommendation, transcript, user, closures, visibilityLost } = get();
    const payload = {
      exportedAt: new Date().toISOString(),
      disclaimer:
        "Synthetic demo scenario export — Palisades Fire 3D Escape Twin. Not official data. Follow official evacuation orders.",
      simParams,
      simMinute,
      closures,
      visibilityLost,
      user,
      recommendation,
      transcript,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `palisades-escape-twin-scenario-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  },
}));
