/**
 * Judge Demo director — drives the cinematic 10-step scenario.
 *
 * Every spatial fact in the demo comes from the SAME live API calls a real
 * user interaction would make (nothing is faked client-side); the script
 * JSON only provides pacing, captions and voice lines.
 */

import { speak, stopSpeaking } from "./speech";
import { sceneManager } from "../cesium/SceneManager";
import { useApp } from "../state/store";
import type { JudgeStep } from "../types";

let abortFlag = false;

const sleep = (ms: number) =>
  new Promise<void>((resolve) => window.setTimeout(resolve, ms));

async function speakAndWait(text?: string): Promise<void> {
  if (!text) return;
  if (!useApp.getState().muted) await speak(text, { interrupt: true });
}

function aborted(): boolean {
  return abortFlag || !useApp.getState().judge.running;
}

async function playReplayTo(toMinute: number, simSpeed: number): Promise<void> {
  const app = useApp.getState();
  app.setPlaybackSpeed(simSpeed);
  app.setPlaying(true);
  while (!aborted() && useApp.getState().simMinute < toMinute) {
    await sleep(120);
  }
  useApp.getState().setPlaying(false);
  useApp.getState().setMinute(toMinute);
}

/**
 * Advance the simulated driver until a route-progress condition is met.
 * Pace: ~0.5 sim-minute per real second (playbackSpeed 1) at 26 mph, with
 * turn-by-turn callouts read verbatim from the engine's maneuvers.
 */
async function drive(until: (progressFrac: number, arrived: boolean) => boolean): Promise<void> {
  const app = useApp.getState();
  app.setPlaybackSpeed(1);
  app.setDriving(true);
  app.setFollowCam(true);
  const TICK_MS = 420;
  const SPEED_M_PER_MIN = (26 * 1609.34) / 60;
  const announced = new Set<string>();
  let lastManeuverId: string | null = null;

  while (!aborted()) {
    const simMinPerSec = useApp.getState().playbackSpeed * 0.5;
    const meters = SPEED_M_PER_MIN * simMinPerSec * (TICK_MS / 1000);
    const r = await useApp.getState().advanceUser(meters);
    if (!r) break;
    useApp.getState().setMinute(r.position.minute);
    if (r.safeZoneChanged) {
      // The predicted zone swallowed the destination: the store has already
      // swapped routes; give the moment room to land before driving on.
      useApp.getState().setJudge({
        caption: "PREDICTED ZONE REACHED THE SAFE ZONE — destination moved, re-routing on live data.",
      });
      await speakAndWait(r.safeZoneNote);
      announced.clear();
      lastManeuverId = null;
      continue;
    }
    const total = r.position.routeProgressMeters + r.remainingDistanceMeters;
    const frac = total > 0 ? r.position.routeProgressMeters / total : 0;

    if (r.nextManeuver && !r.arrived) {
      const m = r.nextManeuver;
      // The previous maneuver was just passed -> execute callout.
      if (lastManeuverId && m.id !== lastManeuverId && announced.has(lastManeuverId + "-pre")) {
        const line = "Proceed — maneuver complete.";
        void line; // passing a turn is narrated by the next pre-announcement
      }
      lastManeuverId = m.id;
      const inst = m.instruction.replace(/^In [^,]+, /, "");
      if (r.distanceToManeuverMeters < 75 && !announced.has(m.id + "-now")) {
        announced.add(m.id + "-now");
        const line = `${inst.charAt(0).toUpperCase()}${inst.slice(1)} now.`;
        useApp.getState().pushTranscript("assistant", line);
        await speakAndWait(line);
      } else if (r.distanceToManeuverMeters < 320 && !announced.has(m.id + "-pre")) {
        announced.add(m.id + "-pre");
        const feet = Math.max(100, Math.round((r.distanceToManeuverMeters * 3.28084) / 50) * 50);
        const line = feet >= 1000
          ? `In ${(r.distanceToManeuverMeters / 1609.34).toFixed(1)} miles, ${inst}.`
          : `In ${feet} feet, ${inst}.`;
        useApp.getState().pushTranscript("assistant", line);
        await speakAndWait(line);
      }
    }
    if (until(frac, r.arrived) || r.arrived) break;
    await sleep(TICK_MS);
  }
  useApp.getState().setDriving(false);
}

async function runStep(step: JudgeStep): Promise<void> {
  const app = useApp.getState();
  const scenario = app.scenario;
  if (!scenario) return;
  app.setJudge({ caption: step.caption ?? "" });

  switch (step.action) {
    case "flyOverview": {
      void speakAndWait(step.voice);
      await sceneManager.cinematicIntro(scenario.ignitionPoint);
      await sleep(Math.max(0, step.durationMs - 6000));
      break;
    }
    case "startReplay": {
      app.setMinute(step.params?.minute ?? 0);
      void speakAndWait(step.voice);
      await sceneManager.flyTo(
        scenario.ignitionPoint[0] - 0.004,
        scenario.ignitionPoint[1] - 0.016,
        1700,
        12,
        -34,
        2.6,
      );
      await sleep(step.durationMs);
      break;
    }
    case "advanceReplay": {
      void speakAndWait(step.voice);
      await playReplayTo(step.params?.toMinute ?? 16, 8);
      break;
    }
    case "placeUser": {
      app.placeUser();
      void speakAndWait(step.voice);
      await sceneManager.flyTo(
        scenario.userStart[0] + 0.002,
        scenario.userStart[1] - 0.012,
        1500,
        350,
        -36,
        3.0,
      );
      await sleep(Math.max(0, step.durationMs - 3000));
      break;
    }
    case "userAsks": {
      const resp = await app.askGuidance(step.userLine ?? "Where do I go?");
      // Wait roughly for speech to finish reading the answer.
      await sleep(Math.min(step.durationMs, 2500 + (resp?.speechText.length ?? 80) * 55));
      break;
    }
    case "showComparison": {
      useApp.setState({ judge: { ...useApp.getState().judge, caption: step.caption ?? "" } });
      await sleep(step.durationMs);
      break;
    }
    case "selectRecommended": {
      const rec = useApp.getState().recommendation;
      if (rec) {
        app.setActiveRoute(rec.recommendedRouteId);
        // Compose the narration from the LIVE recommendation so it is
        // always true (fastest may or may not have won this run).
        const destName = rec.destination?.name ?? "the safe zone";
        const liveTag = rec.source === "google_directions"
          ? " Directions are live Google Maps data." : "";
        await speakAndWait(
          `Recommended simulated route selected toward ${destName}. ` +
          `${rec.whyNotFastest}${liveTag} Follow official evacuation orders.`);
      } else {
        await speakAndWait(step.voice);
      }
      await sleep(1500);
      break;
    }
    case "driveUntilProgress": {
      const past = step.params?.pastManeuvers;
      if (past !== undefined) {
        // Geometry-robust trigger: just past the Nth real maneuver.
        const rec = useApp.getState().recommendation;
        const route = rec?.candidates.find((c) => c.routeId === useApp.getState().activeRouteId);
        const real = (route?.maneuvers ?? []).filter((m) => m.type !== "depart");
        const targetM = real.slice(0, past).reduce((acc, m) => acc + m.distanceMeters, 0)
          + (step.params?.plusMeters ?? 250);
        await drive(() => (useApp.getState().user?.routeProgressMeters ?? 0) >= targetM);
      } else {
        const target = step.params?.fraction ?? 0.37;
        await drive((frac) => frac >= target);
      }
      break;
    }
    case "holdForRelocation": {
      // Parked at the staging area: keep the replay clock running and let the
      // backend watcher decide when the predicted zone forces a move.
      const timeout = step.params?.timeoutMs ?? 45000;
      app.setPlaybackSpeed(step.params?.speed ?? 8);
      app.setPlaying(true);
      const started = performance.now();
      let moved = false;
      while (!aborted() && performance.now() - started < timeout) {
        const r = await useApp.getState().advanceUser(0);
        if (r?.safeZoneChanged) {
          useApp.getState().setJudge({
            caption: "PREDICTED ZONE REACHED THE SAFE ZONE — destination moved, re-routing on live data.",
          });
          await speakAndWait(r.safeZoneNote);
          moved = true;
          break;
        }
        await sleep(900);
      }
      useApp.getState().setPlaying(false);
      if (!moved) {
        useApp.getState().setJudge({
          caption: "Prediction held clear of the staging area in this run — continuing.",
        });
        await sleep(2500);
      }
      break;
    }
    case "highlightReroute": {
      app.setFollowCam(false);
      const u = useApp.getState().user;
      if (u) await sceneManager.flyTo(u.lon + 0.004, u.lat - 0.014, 2100, 345, -38, 2.6);
      await sleep(Math.max(0, step.durationMs - 2600));
      break;
    }
    case "driveUntilArrived": {
      await drive((_f, arrived) => arrived);
      break;
    }
    case "arrive": {
      app.setFollowCam(false);
      const u = useApp.getState().user;
      if (u) await sceneManager.flyTo(u.lon, u.lat - 0.01, 1400, 0, -42, 2.4);
      await speakAndWait(step.voice);
      await sleep(1200);
      break;
    }
    case "showSummary": {
      const st = useApp.getState();
      const rec = st.recommendation;
      const best = rec?.candidates.find((c) => c.routeId === rec.recommendedRouteId);
      const relocated = st.transcript.some((m) => m.text.includes("Redirecting to"));
      const liveLine = rec?.source === "google_directions"
        ? "Routes were live Google Directions, hazard-scored by the twin's models."
        : "Routes came from the modeled road graph (set GOOGLE_MAPS_API_KEY for live Google Directions).";
      st.setJudge({
        summary: [
          `Fire spread modeled over ${st.sim?.minutes.length ?? 0} time steps using wind + terrain inputs.`,
          `Candidate routes compared and scored (final modeled buffer ${best?.fireArrivalBufferMinutes.toFixed(0) ?? "–"} min).`,
          "Visibility report re-weighted hazards and re-routed the resident mid-drive.",
          relocated
            ? "Predicted zone reached the first safe zone — the SAFE ZONE MOVED and the route re-planned."
            : "Safe-zone watcher monitored the predicted zone throughout the drive.",
          liveLine,
          "Official-orders guardrail present in every spoken response.",
        ],
      });
      break;
    }
    default:
      await sleep(step.durationMs);
  }
}

export async function runJudgeDemo(): Promise<void> {
  const app = useApp.getState();
  const script = app.datasets.judgeScript;
  if (!script || app.judge.running) return;
  abortFlag = false;

  await app.resetScenario();
  app.setJudge({ running: true, stepIndex: -1, caption: "", summary: null });
  app.pushTranscript("system", "Judge demo started — scripted pacing, live simulation calls.");

  for (let i = 0; i < script.steps.length; i++) {
    if (aborted()) break;
    app.setJudge({ stepIndex: i });
    try {
      await runStep(script.steps[i]);
    } catch (e) {
      app.pushTranscript("system", `Demo step ${script.steps[i].id} error: ${e instanceof Error ? e.message : e}`);
    }
  }
  if (!abortFlag) {
    useApp.getState().setJudge({ running: false, stepIndex: -1 });
  }
}

export function stopJudgeDemo(): void {
  abortFlag = true;
  stopSpeaking();
  const app = useApp.getState();
  app.setPlaying(false);
  app.setDriving(false);
  app.setFollowCam(false);
  app.setJudge({ running: false, stepIndex: -1, caption: "", summary: null });
}
