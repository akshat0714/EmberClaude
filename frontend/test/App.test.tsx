/**
 * Frontend smoke tests: the app shell renders with its core affordances,
 * without booting Cesium (mocked) or a live backend (mocked client).
 */

import { render, screen } from "@testing-library/react";
import { vi, describe, it, expect, beforeAll } from "vitest";

vi.mock("../src/cesium/CesiumScene", () => ({
  default: () => <div data-testid="cesium-scene-mock" />,
}));

vi.mock("../src/cesium/SceneManager", () => ({
  sceneManager: { viewer: null, init: vi.fn(), setFollow: vi.fn() },
}));

vi.mock("../src/api/client", () => ({
  api: {
    health: vi.fn().mockResolvedValue({ status: "ok" }),
    scenario: vi.fn().mockResolvedValue({
      name: "palisades-demo",
      label: "Historical Palisades Fire Replay + Simulated Evacuation",
      center: [-118.527, 34.043],
      bounds: [-118.6, 33.995, -118.435, 34.105],
      ignitionPoint: [-118.5421, 34.0708],
      ignitionTimeLocal: "2025-01-07T10:30:00-08:00",
      defaults: { windSpeedMph: 38, windFromDeg: 12, fireIntensity: 0.85, nowMinute: 0, horizonMinutes: 75 },
      timelineMinutes: [0, 5, 10, 15, 20, 30, 45, 60],
      userStart: [-118.5392, 34.0648],
      safeZones: [],
      datasets: { roads: "/data/r", buildings: "/data/b", vegetation: "/data/v", judgeScript: "/data/j" },
      disclaimers: ["Simulation only."],
    }),
    profiles: vi.fn().mockResolvedValue([]),
    dataset: vi.fn().mockResolvedValue({ type: "FeatureCollection", features: [] }),
    judgeScript: vi.fn().mockResolvedValue({ title: "demo", steps: [], disclaimer: "" }),
    reset: vi.fn().mockResolvedValue({ status: "reset" }),
    runSimulation: vi.fn().mockResolvedValue({
      params: { windSpeedMph: 38, windFromDeg: 12, fireIntensity: 0.85, nowMinute: 0, horizonMinutes: 75 },
      minutes: [0],
      ignitionPoint: [-118.5421, 34.0708],
      fireCellsByMinute: {},
      predictedFireCellsByMinute: {},
      firePerimeterByMinute: {},
      riskZonesByMinute: {},
      smokeZonesByMinute: {},
      uncertaintyEnvelopeByMinute: {},
      modelNotes: [],
      disclaimer: "",
    }),
    recommendRoutes: vi.fn(),
    guidance: vi.fn(),
    advance: vi.fn(),
    deviate: vi.fn(),
  },
}));

import App from "../src/App";

beforeAll(() => {
  // jsdom lacks these browser APIs used by the app shell.
  Object.defineProperty(window, "speechSynthesis", {
    value: { cancel: vi.fn(), speak: vi.fn(), getVoices: () => [], onvoiceschanged: null },
    writable: true,
  });
});

describe("App shell", () => {
  it("renders the title, safety banner and judge demo button", async () => {
    render(<App />);
    expect((await screen.findAllByText(/3D ESCAPE TWIN/i)).length).toBeGreaterThan(0);
    expect(
      (await screen.findAllByText(/follow official evacuation orders and emergency personnel/i)).length,
    ).toBeGreaterThan(0);
    const judgeBtn = screen.getByTestId("judge-demo-button");
    expect(judgeBtn.textContent).toMatch(/RUN JUDGE DEMO/i);
  });

  it("shows the historical replay timeline", async () => {
    render(<App />);
    expect((await screen.findAllByText(/HISTORICAL REPLAY/i)).length).toBeGreaterThan(0);
  });
});
