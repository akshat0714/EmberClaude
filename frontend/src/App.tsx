import { useEffect, lazy, Suspense } from "react";
import { useApp } from "./state/store";
import TopBar from "./components/TopBar";
import LeftPanel from "./components/LeftPanel";
import RightPanel from "./components/RightPanel";
import TimelineBar from "./components/TimelineBar";
import { JudgeOverlay, LoadingScreen, Toast } from "./components/Overlays";

// Cesium is heavy; load the scene lazily so the ops shell paints instantly.
const CesiumScene = lazy(() => import("./cesium/CesiumScene"));

export default function App() {
  const boot = useApp((s) => s.boot);
  const loading = useApp((s) => s.loading);
  const bootError = useApp((s) => s.bootError);
  const playing = useApp((s) => s.playing);

  useEffect(() => {
    void boot();
  }, [boot]);

  // Replay clock: playbackSpeed × 0.5 simulated minutes per real second.
  useEffect(() => {
    if (!playing) return;
    let last = performance.now();
    const id = window.setInterval(() => {
      const now = performance.now();
      const dt = (now - last) / 1000;
      last = now;
      const s = useApp.getState();
      const next = s.simMinute + dt * s.playbackSpeed * 0.5;
      s.setMinute(next);
      if (next >= 90) s.setPlaying(false);
    }, 120);
    return () => window.clearInterval(id);
  }, [playing]);

  return (
    <div className="flex h-full flex-col">
      <TopBar />
      <div className="relative flex min-h-0 flex-1">
        <LeftPanel />
        <main className="relative min-w-0 flex-1 bg-ops-900">
          <Suspense fallback={<div className="absolute inset-0 bg-ops-900" />}>
            {!bootError && <CesiumScene />}
          </Suspense>
          <JudgeOverlay />
          <Toast />
        </main>
        <RightPanel />
      </div>
      <TimelineBar />
      {(loading || bootError) && <LoadingScreen />}
    </div>
  );
}
