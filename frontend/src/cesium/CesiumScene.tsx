/** React wrapper that binds store state to the imperative SceneManager. */

import { useEffect, useRef } from "react";
import { useApp } from "../state/store";
import { sceneManager } from "./SceneManager";

export default function CesiumScene() {
  const ref = useRef<HTMLDivElement>(null);
  const inited = useRef(false);

  const scenario = useApp((s) => s.scenario);
  const datasets = useApp((s) => s.datasets);
  const sim = useApp((s) => s.sim);
  const simMinute = useApp((s) => s.simMinute);
  const layers = useApp((s) => s.layers);
  const user = useApp((s) => s.user);
  const recommendation = useApp((s) => s.recommendation);
  const activeRouteId = useApp((s) => s.activeRouteId);
  const reportedZone = useApp((s) => s.reportedZone);
  const followCam = useApp((s) => s.followCam);
  const setLoading = useApp((s) => s.setLoadingStage);

  // One-time viewer init.
  useEffect(() => {
    if (!ref.current || inited.current) return;
    inited.current = true;
    void sceneManager.init(ref.current).then(() => {
      setLoading("Scene ready");
      useApp.setState({ loading: false });
    });
    return () => {
      // Keep the viewer alive across React StrictMode remounts in dev.
    };
  }, [setLoading]);

  // Static world once scenario + datasets are in.
  useEffect(() => {
    if (!scenario || !datasets.roads || !datasets.buildings || !datasets.vegetation) return;
    if (!sceneManager.viewer) return;
    sceneManager.loadStaticWorld(
      datasets.roads,
      datasets.buildings,
      datasets.vegetation,
      scenario.safeZones,
      scenario.ignitionPoint,
      scenario.userStart,
    );
  }, [scenario, datasets]);

  useEffect(() => {
    if (!sim || !sceneManager.viewer) return;
    sceneManager.renderFireFrame(sim, simMinute);
    sceneManager.setClockMinute(simMinute);
  }, [sim, simMinute]);

  useEffect(() => {
    if (!sceneManager.viewer) return;
    sceneManager.applyLayerToggles(layers);
  }, [layers]);

  useEffect(() => {
    if (!sceneManager.viewer) return;
    sceneManager.renderUser(user);
  }, [user]);

  useEffect(() => {
    if (!sceneManager.viewer) return;
    sceneManager.renderRoutes(recommendation ?? null, activeRouteId);
  }, [recommendation, activeRouteId]);

  useEffect(() => {
    if (!sceneManager.viewer) return;
    sceneManager.renderReportedZone(reportedZone);
  }, [reportedZone]);

  useEffect(() => {
    if (!sceneManager.viewer) return;
    sceneManager.setFollow(followCam);
  }, [followCam]);

  return <div ref={ref} className="absolute inset-0" data-testid="cesium-scene" />;
}
