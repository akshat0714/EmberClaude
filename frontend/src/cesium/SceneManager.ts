/**
 * SceneManager — owns the Cesium viewer and every 3D layer.
 *
 * Design notes:
 * - No Cesium Ion token: imagery comes from CARTO's dark basemap (with an
 *   offline NaturalEarthII fallback shipped inside Cesium), terrain from the
 *   analytic Palisades heightfield in lib/terrain.ts.
 * - All overlays are Cesium entities/primitives (deck.gl was evaluated and
 *   skipped in v1 — see docs/ARCHITECTURE.md).
 * - Heights are computed from the same terrain function the terrain provider
 *   uses, so nothing ever floats or sinks.
 */

import * as Cesium from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";
import type {
  CandidateRoute,
  GeoCollection,
  LonLat,
  RouteRecommendation,
  SafeZone,
  SimulationResult,
  UserPosition,
} from "../types";
import { bearingDeg, haversineM } from "../lib/geo";
import { createTwinTerrainProvider, groundPosition, terrainHeightM } from "../lib/terrain";
import type { LayerToggles } from "../state/store";

const START_ISO = "2025-01-07T18:30:00Z"; // Jan 7 2025, 10:30 PST

const COLORS = {
  fireCore: Cesium.Color.fromCssColorString("#ffd166"),
  fireMid: Cesium.Color.fromCssColorString("#ff7a2f"),
  fireDeep: Cesium.Color.fromCssColorString("#d52b04"),
  perimeter: Cesium.Color.fromCssColorString("#ff3d00"),
  predicted: Cesium.Color.fromCssColorString("#ffae42"),
  uncertainty: Cesium.Color.fromCssColorString("#ffd27a"),
  smoke: Cesium.Color.fromCssColorString("#9aa3ad"),
  route: Cesium.Color.fromCssColorString("#38bdf8"),
  routeAlt: Cesium.Color.fromCssColorString("#64748b"),
  user: Cesium.Color.fromCssColorString("#2f9bff"),
  safe: Cesium.Color.fromCssColorString("#34d399"),
  risk: {
    extreme: Cesium.Color.fromCssColorString("#ff1f00"),
    high: Cesium.Color.fromCssColorString("#ff7a00"),
    elevated: Cesium.Color.fromCssColorString("#ffc53d"),
  } as Record<string, Cesium.Color>,
};

function fireParticleImage(): HTMLCanvasElement {
  const c = document.createElement("canvas");
  c.width = c.height = 48;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(24, 24, 2, 24, 24, 24);
  grad.addColorStop(0, "rgba(255,240,200,1)");
  grad.addColorStop(0.35, "rgba(255,150,60,0.85)");
  grad.addColorStop(1, "rgba(255,60,0,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 48, 48);
  return c;
}

function smokeParticleImage(): HTMLCanvasElement {
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(32, 32, 4, 32, 32, 32);
  grad.addColorStop(0, "rgba(120,124,130,0.55)");
  grad.addColorStop(1, "rgba(90,94,100,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 64, 64);
  return c;
}

export class SceneManager {
  viewer!: Cesium.Viewer;
  private staticDS = new Cesium.CustomDataSource("static");
  private fireDS = new Cesium.CustomDataSource("fire");
  private hazardDS = new Cesium.CustomDataSource("hazard");
  private routeDS = new Cesium.CustomDataSource("route");
  private userDS = new Cesium.CustomDataSource("user");
  private cellEntities = new Map<string, Cesium.Entity>();
  private cellIntensity = new Map<string, number>();
  private pulse = 0;
  private renderedMinuteKey = "";
  private renderedSim: SimulationResult | null = null;
  private fireParticles: Cesium.ParticleSystem | null = null;
  private smokeParticles: Cesium.ParticleSystem | null = null;
  private userEntity: Cesium.Entity | null = null;
  private userPos: { lon: number; lat: number; heading: number } | null = null;
  private follow = false;
  private layerFolders: Record<string, Cesium.Entity[]> = {};
  destroyed = false;

  /** True when WebGL is software-rendered (CI, VMs, old machines). */
  private softwareGL = false;
  /** Live mode: Google Photorealistic 3D Tiles carry the real world. */
  private googleMode = false;
  private safeZoneEntities = new Map<string, Cesium.Entity>();

  private detectSoftwareGL(): boolean {
    try {
      const gl = document.createElement("canvas").getContext("webgl");
      const dbg = gl?.getExtension("WEBGL_debug_renderer_info");
      const renderer = dbg ? String(gl!.getParameter(dbg.UNMASKED_RENDERER_WEBGL)) : "";
      return /swiftshader|llvmpipe|software|basic render/i.test(renderer);
    } catch {
      return false;
    }
  }

  async init(container: HTMLElement, googleMapsApiKey = ""): Promise<void> {
    Cesium.Ion.defaultAccessToken = "";
    this.softwareGL = this.detectSoftwareGL();
    this.googleMode = Boolean(googleMapsApiKey);
    const imagery = new Cesium.ImageryLayer(
      new Cesium.UrlTemplateImageryProvider({
        url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        subdomains: ["a", "b", "c", "d"],
        credit: new Cesium.Credit("© OpenStreetMap contributors © CARTO"),
        maximumLevel: 18,
      }),
    );

    this.viewer = new Cesium.Viewer(container, {
      baseLayer: imagery,
      terrainProvider: createTwinTerrainProvider(),
      animation: false,
      timeline: false,
      baseLayerPicker: false,
      fullscreenButton: false,
      geocoder: false,
      homeButton: false,
      sceneModePicker: false,
      navigationHelpButton: false,
      selectionIndicator: false,
      infoBox: false,
      requestRenderMode: false,
    });

    const { scene, clock } = this.viewer;
    scene.globe.baseColor = Cesium.Color.fromCssColorString("#060a14");
    scene.globe.enableLighting = true;
    scene.globe.atmosphereBrightnessShift = -0.15;
    scene.fog.enabled = true;
    scene.fog.density = 0.00012;
    if (scene.skyAtmosphere) scene.skyAtmosphere.brightnessShift = -0.25;
    imagery.brightness = 0.7;
    imagery.saturation = 0.85;
    imagery.gamma = 1.05;

    // Offline fallback if the dark basemap is unreachable.
    let fellBack = false;
    imagery.imageryProvider.errorEvent.addEventListener(() => {
      if (fellBack) return;
      fellBack = true;
      void Cesium.TileMapServiceImageryProvider.fromUrl(
        Cesium.buildModuleUrl("Assets/Textures/NaturalEarthII"),
      ).then((provider) => {
        if (this.destroyed) return;
        this.viewer.imageryLayers.removeAll();
        const layer = this.viewer.imageryLayers.addImageryProvider(provider);
        layer.brightness = 0.55;
        layer.saturation = 0.5;
      });
    });

    try {
      const bloom = scene.postProcessStages.bloom;
      bloom.enabled = !this.softwareGL; // gaussian passes melt software rasterizers
      bloom.uniforms.glowOnly = false;
      bloom.uniforms.contrast = 119;
      bloom.uniforms.brightness = -0.25;
      bloom.uniforms.sigma = 3.0;
    } catch {
      /* bloom unsupported -> fine */
    }
    if (this.softwareGL) {
      this.viewer.resolutionScale = 0.55;
      scene.fog.enabled = false;
      scene.globe.enableLighting = false;
    }

    clock.currentTime = Cesium.JulianDate.fromIso8601(START_ISO);
    clock.shouldAnimate = false;

    // LIVE MODE: Google Photorealistic 3D Tiles of the real Pacific
    // Palisades (Map Tiles API). Required attribution stays on screen.
    if (this.googleMode) {
      try {
        const tileset = await Cesium.Cesium3DTileset.fromUrl(
          `https://tile.googleapis.com/v1/3dtiles/root.json?key=${googleMapsApiKey}`,
          { showCreditsOnScreen: true },
        );
        this.viewer.scene.primitives.add(tileset);
        scene.globe.show = false; // the tiles ARE the world
        this.viewer.imageryLayers.removeAll();
      } catch {
        this.googleMode = false; // tiles unreachable -> synthetic twin still works
      }
    }

    for (const ds of [this.staticDS, this.fireDS, this.hazardDS, this.routeDS, this.userDS]) {
      await this.viewer.dataSources.add(ds);
    }

    scene.preUpdate.addEventListener(() => {
      this.pulse = performance.now() / 1000;
      if (this.follow && this.userPos) {
        const { lon, lat, heading } = this.userPos;
        this.viewer.camera.lookAt(
          groundPosition(lon, lat, 12),
          new Cesium.HeadingPitchRange(
            Cesium.Math.toRadians(heading),
            Cesium.Math.toRadians(-32),
            850,
          ),
        );
      }
    });

    this.homeView(0);
  }

  /** Polyline graphics that hug the world in BOTH modes: draped onto the
   * Google 3D tiles in live mode, explicit terrain heights in twin mode. */
  private lineOn(coords: Array<[number, number] | number[]>, offsetM: number, width: number,
                 material: Cesium.MaterialProperty | Cesium.Color): Cesium.PolylineGraphics.ConstructorOptions {
    if (this.googleMode) {
      return {
        positions: coords.map((p) => Cesium.Cartesian3.fromDegrees(p[0], p[1])),
        clampToGround: true,
        classificationType: Cesium.ClassificationType.BOTH,
        width,
        material,
      };
    }
    return {
      positions: coords.map((p) => groundPosition(p[0], p[1], offsetM)),
      width,
      material,
    };
  }

  /** Filled disc that drapes correctly in both modes. */
  private discOn(lon: number, lat: number, radius: number,
                 material: Cesium.MaterialProperty | Cesium.Color,
                 outlineColor?: Cesium.Color): Cesium.EllipseGraphics.ConstructorOptions {
    const base: Cesium.EllipseGraphics.ConstructorOptions = {
      semiMajorAxis: radius,
      semiMinorAxis: radius,
      material,
      outline: Boolean(outlineColor),
      outlineColor,
    };
    if (this.googleMode) {
      base.classificationType = Cesium.ClassificationType.BOTH;
    } else {
      base.height = Math.max(terrainHeightM(lon, lat), 0) + 1.5;
    }
    return base;
  }

  setClockMinute(minute: number): void {
    const t = Cesium.JulianDate.fromIso8601(START_ISO);
    this.viewer.clock.currentTime = Cesium.JulianDate.addMinutes(t, minute, new Cesium.JulianDate());
  }

  // ---- camera ---------------------------------------------------------------

  homeView(duration = 2.4): void {
    this.viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(-118.545, 33.985, 6400),
      orientation: { heading: Cesium.Math.toRadians(14), pitch: Cesium.Math.toRadians(-34), roll: 0 },
      duration,
    });
  }

  flyTo(lon: number, lat: number, height: number, headingDeg: number, pitchDeg: number, duration = 3): Promise<void> {
    return new Promise((resolve) => {
      this.viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(lon, lat, height),
        orientation: {
          heading: Cesium.Math.toRadians(headingDeg),
          pitch: Cesium.Math.toRadians(pitchDeg),
          roll: 0,
        },
        duration,
        complete: resolve,
        cancel: resolve,
      });
    });
  }

  async cinematicIntro(ignition: LonLat): Promise<void> {
    await this.flyTo(-118.560, 33.992, 7200, 16, -32, 2.8);
    await this.flyTo(ignition[0] - 0.012, ignition[1] - 0.020, 2300, 22, -30, 3.4);
  }

  setFollow(follow: boolean): void {
    this.follow = follow;
    if (!follow) this.viewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
  }

  // ---- static world ----------------------------------------------------------

  loadStaticWorld(
    roads: GeoCollection,
    buildings: GeoCollection,
    vegetation: GeoCollection,
    safeZones: SafeZone[],
    ignition: LonLat,
    userStart: LonLat,
  ): void {
    const ents = this.staticDS.entities;
    ents.removeAll();
    this.layerFolders = { buildings: [], vegetation: [], labels: [] };

    // Vegetation / fuel zones — muted translucent ground polygons.
    for (const f of vegetation.features) {
      const coords = (f.geometry.coordinates as number[][][])[0];
      const fuel = (f.properties.fuelLoad as number) ?? 0.5;
      const urban = (f.properties.kind as string)?.includes("urban");
      const color = urban
        ? Cesium.Color.fromCssColorString("#2c4a3e").withAlpha(0.10)
        : Cesium.Color.fromBytes(46 + fuel * 50, 84 - fuel * 18, 38, 26 + fuel * 60);
      const e = ents.add({
        polygon: {
          hierarchy: new Cesium.PolygonHierarchy(
            coords.map(([lon, lat]) => Cesium.Cartesian3.fromDegrees(lon, lat)),
          ),
          material: color,
          classificationType: Cesium.ClassificationType.BOTH,
        },
      });
      this.layerFolders.vegetation.push(e);
    }

    // Roads with explicit terrain-following heights.
    const labelDone = new Set<string>();
    for (const f of roads.features) {
      const coords = f.geometry.coordinates as LonLat[];
      const cls = f.properties.class as string;
      const name = (f.properties.name as string) || "";
      const style: Record<string, [string, number]> = {
        highway: ["#93a8c4", 5],
        arterial: ["#7e93ad", 4],
        canyon: ["#6c8099", 3.5],
        residential_visual: ["#36465e", 1.6],
      };
      const [color, width] = style[cls] ?? ["#56688a", 2];
      ents.add({
        polyline: this.lineOn(coords, 2.5, width,
          Cesium.Color.fromCssColorString(color).withAlpha(cls === "residential_visual" ? 0.5 : 0.9)),
      });
      if (name && !labelDone.has(name) && coords.length > 2) {
        labelDone.add(name);
        const mid = coords[Math.floor(coords.length / 2)];
        const e = ents.add({
          position: groundPosition(mid[0], mid[1], 26),
          label: {
            text: name.toUpperCase(),
            font: "600 11px Inter, sans-serif",
            fillColor: Cesium.Color.fromCssColorString("#aebed4"),
            outlineColor: Cesium.Color.BLACK.withAlpha(0.9),
            outlineWidth: 3,
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 13000),
            translucencyByDistance: new Cesium.NearFarScalar(2200, 1, 12500, 0),
          },
        });
        this.layerFolders.labels.push(e);
      }
    }

    // Buildings — extruded synthetic footprints.
    for (const f of buildings.features) {
      const coords = (f.geometry.coordinates as number[][][])[0];
      const h = (f.properties.heightM as number) ?? 5;
      const kind = f.properties.kind as string;
      const [clon, clat] = coords[0];
      const base = terrainHeightM(clon, clat);
      const tint = 0.88 + ((Math.abs(clon * 7919 + clat * 104729) * 1000) % 24) / 100;
      const base_color = Cesium.Color.fromCssColorString(kind === "commercial" ? "#3d4f6e" : "#2c3a54");
      const color = Cesium.Color.multiplyByScalar(base_color, tint, new Cesium.Color());
      const e = ents.add({
        polygon: {
          hierarchy: new Cesium.PolygonHierarchy(
            coords.map(([lon, lat]) => Cesium.Cartesian3.fromDegrees(lon, lat)),
          ),
          height: Math.max(base, 0),
          extrudedHeight: Math.max(base, 0) + h,
          material: color.withAlpha(0.96),
          outline: false,
          shadows: Cesium.ShadowMode.DISABLED,
        },
      });
      this.layerFolders.buildings.push(e);
    }

    // Safe zones render via renderSafeZones (status-aware, dynamic).
    this.renderSafeZones(safeZones.map((z) => ({
      zone: z, status: "safe", bufferMinutes: 999, insidePredictedZone: false, note: "",
    })), null);

    // Ignition marker.
    ents.add({
      position: groundPosition(ignition[0], ignition[1], 8),
      point: { pixelSize: 9, color: COLORS.fireDeep, outlineColor: COLORS.fireCore, outlineWidth: 2 },
      label: {
        text: "IGNITION  ·  ~10:30 AM JAN 7 (MODELED)",
        font: "600 11px Inter, sans-serif",
        fillColor: Cesium.Color.fromCssColorString("#ffb265"),
        outlineColor: Cesium.Color.BLACK.withAlpha(0.9),
        outlineWidth: 3,
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        pixelOffset: new Cesium.Cartesian2(0, -16),
        distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 30000),
      },
    });

    // User start hint (before the dot is placed).
    ents.add({
      position: groundPosition(userStart[0], userStart[1], 4),
      ellipse: this.discOn(userStart[0], userStart[1], 90,
        COLORS.user.withAlpha(0.08), COLORS.user.withAlpha(0.4)),
    });
  }

  applyLayerToggles(layers: LayerToggles): void {
    for (const e of this.layerFolders.buildings ?? []) e.show = layers.buildings;
    for (const e of this.layerFolders.vegetation ?? []) e.show = layers.vegetation;
    for (const e of this.layerFolders.labels ?? []) e.show = layers.labels;
    this.hazardLayerToggles = layers;
    if (this.renderedSim) this.renderFireFrame(this.renderedSim, this.lastMinute, true);
  }

  private hazardLayerToggles: LayerToggles = {
    buildings: true,
    vegetation: true,
    smoke: true,
    risk: true,
    uncertainty: true,
    predicted: true,
    labels: true,
  };
  private lastMinute = 0;

  // ---- fire frame -------------------------------------------------------------

  frameKey(sim: SimulationResult, minute: number): string {
    const frames = sim.minutes.filter((m) => m <= minute);
    return String(frames.length ? Math.max(...frames) : sim.minutes[0]);
  }

  renderFireFrame(sim: SimulationResult, minute: number, force = false): void {
    this.lastMinute = minute;
    const key = this.frameKey(sim, minute);
    const newSim = this.renderedSim !== sim;
    if (!force && !newSim && key === this.renderedMinuteKey) return;
    this.renderedMinuteKey = key;
    if (newSim) {
      this.cellEntities.clear();
      this.fireDS.entities.removeAll();
    }
    this.renderedSim = sim;
    const layers = this.hazardLayerToggles;

    // -- fire cells (incremental: cells only accumulate as time advances) --
    const cells = sim.fireCellsByMinute[key] ?? [];
    const liveIds = new Set<string>();
    for (const cell of cells) {
      liveIds.add(cell.id);
      const existing = this.cellEntities.get(cell.id);
      const inten = cell.intensity;
      const color = Cesium.Color.lerp(
        COLORS.fireDeep,
        COLORS.fireCore,
        Math.min(1, inten * 1.15),
        new Cesium.Color(),
      );
      this.cellIntensity.set(cell.id, inten);
      if (existing) continue;
      const seed = (cell.lon * 9301 + cell.lat * 49297) % 6.28;
      // STATIC geometry (dynamic ellipse axes would re-tessellate every frame
      // and melt the renderer at 100+ cells); the burn "breathes" via alpha.
      const baseColor = color;
      const e = this.fireDS.entities.add({
        position: groundPosition(cell.lon, cell.lat, 2),
        ellipse: {
          semiMajorAxis: cell.radiusMeters * 1.12,
          semiMinorAxis: cell.radiusMeters * 0.92,
          rotation: seed,
          material: new Cesium.ColorMaterialProperty(
            new Cesium.CallbackProperty(() => {
              const inten2 = this.cellIntensity.get(cell.id) ?? inten;
              const breathe = 0.86 + 0.14 * Math.sin(this.pulse * 2.2 + seed);
              return baseColor.withAlpha((0.30 + 0.40 * inten2) * breathe);
            }, false),
          ),
          ...(this.googleMode
            ? { classificationType: Cesium.ClassificationType.BOTH }
            : { height: Math.max(terrainHeightM(cell.lon, cell.lat), 0) + 1.5 }),
        },
        point:
          inten > 0.45
            ? {
                pixelSize: 6 + inten * 9,
                color: COLORS.fireMid.withAlpha(0.9),
                scaleByDistance: new Cesium.NearFarScalar(800, 1.4, 16000, 0.35),
              }
            : undefined,
      });
      this.cellEntities.set(cell.id, e);
    }
    for (const [id, e] of this.cellEntities) {
      e.show = liveIds.has(id);
      if (!liveIds.has(id) && !e.show) continue;
    }

    // -- replace per-frame overlay entities --
    const overlayIds = this.fireDS.entities.values.filter((e) => e.id.toString().startsWith("ov-"));
    for (const e of overlayIds) this.fireDS.entities.remove(e);

    const perim = sim.firePerimeterByMinute[key];
    if (perim) {
      this.fireDS.entities.add({
        id: `ov-perim-${key}`,
        polyline: this.lineOn(perim.polygon, 5, 9,
          new Cesium.PolylineGlowMaterialProperty({
            color: COLORS.perimeter.withAlpha(0.95),
            glowPower: 0.28,
            taperPower: 1,
          })),
      });
    }

    // predicted +15 min perimeter (dashed)
    if (layers.predicted) {
      const target = Number(key) + 15;
      const predKey = String(
        sim.minutes.reduce(
          (best, m) => (Math.abs(m - target) < Math.abs(best - target) ? m : best),
          sim.minutes[0],
        ),
      );
      const pred = sim.firePerimeterByMinute[predKey];
      if (pred && Number(predKey) > Number(key)) {
        this.fireDS.entities.add({
          id: `ov-pred-${key}`,
          polyline: this.lineOn(pred.polygon, 5, 3.5,
            new Cesium.PolylineDashMaterialProperty({
              color: COLORS.predicted.withAlpha(0.9),
              dashLength: 22,
            })),
        });
      }
    }

    if (layers.uncertainty) {
      const env = sim.uncertaintyEnvelopeByMinute[key];
      if (env) {
        this.fireDS.entities.add({
          id: `ov-env-${key}`,
          polyline: this.lineOn(env.polygon, 5, 2.2,
            new Cesium.PolylineDashMaterialProperty({
              color: COLORS.uncertainty.withAlpha(0.55),
              dashLength: 9,
            })),
        });
      }
    }

    if (layers.risk) {
      for (const rz of sim.riskZonesByMinute[key] ?? []) {
        const color = COLORS.risk[rz.level] ?? COLORS.risk.elevated;
        this.fireDS.entities.add({
          id: `ov-risk-${rz.id}`,
          polygon: {
            hierarchy: new Cesium.PolygonHierarchy(
              rz.polygon.map(([lon, lat]) => Cesium.Cartesian3.fromDegrees(lon, lat)),
            ),
            material: color.withAlpha(rz.level === "extreme" ? 0.16 : rz.level === "high" ? 0.11 : 0.07),
            classificationType: Cesium.ClassificationType.BOTH,
          },
        });
      }
    }

    if (layers.smoke) {
      for (const sz of sim.smokeZonesByMinute[key] ?? []) {
        this.fireDS.entities.add({
          id: `ov-smoke-${sz.id}`,
          polygon: {
            hierarchy: new Cesium.PolygonHierarchy(
              sz.polygon.map(([lon, lat]) => Cesium.Cartesian3.fromDegrees(lon, lat)),
            ),
            material: COLORS.smoke.withAlpha(0.07 + sz.density * 0.16),
            classificationType: Cesium.ClassificationType.BOTH,
          },
        });
        // 3D smoke volume along the main plume centerlines.
        if (sz.id.includes("main") && !this.softwareGL) {
          const pts = sz.centerline;
          for (let i = 0; i < pts.length; i++) {
            const [lon, lat] = pts[i];
            const f = i / Math.max(1, pts.length - 1);
            const r = 220 + f * 620 + sz.density * 240;
            const drift = i * 37;
            this.fireDS.entities.add({
              id: `ov-puff-${sz.id}-${i}`,
              position: new Cesium.CallbackPositionProperty(
                () =>
                  Cesium.Cartesian3.fromDegrees(
                    lon + Math.sin(this.pulse * 0.12 + drift) * 0.0006 * f,
                    lat,
                    Math.max(terrainHeightM(lon, lat), 0) +
                      120 +
                      f * sz.plumeHeightMeters +
                      Math.sin(this.pulse * 0.4 + drift) * 18,
                  ),
                false,
              ),
              ellipsoid: {
                radii: new Cesium.Cartesian3(r, r, r * 0.45),
                material: COLORS.smoke.withAlpha(0.05 + sz.density * 0.10),
              },
            });
          }
        }
      }
    }

    this.updateParticles(sim, key);
  }

  private updateParticles(sim: SimulationResult, key: string): void {
    if (this.softwareGL) return; // particle fill cost is prohibitive without a GPU
    const cells = (sim.fireCellsByMinute[key] ?? [])
      .slice()
      .sort((a, b) => b.intensity - a.intensity);
    if (!cells.length) {
      this.fireParticles && (this.fireParticles.show = false);
      this.smokeParticles && (this.smokeParticles.show = false);
      return;
    }
    const top = cells[0];
    const pos = groundPosition(top.lon, top.lat, 12);
    const modelMatrix = Cesium.Transforms.eastNorthUpToFixedFrame(pos);
    const windToRad = Cesium.Math.toRadians((sim.params.windFromDeg + 180) % 360);
    const driftX = Math.sin(windToRad) * 9;
    const driftY = Math.cos(windToRad) * 9;

    if (!this.fireParticles) {
      this.fireParticles = this.viewer.scene.primitives.add(
        new Cesium.ParticleSystem({
          image: fireParticleImage(),
          startColor: Cesium.Color.fromCssColorString("#ffdd99").withAlpha(0.9),
          endColor: Cesium.Color.fromCssColorString("#ff3300").withAlpha(0.0),
          startScale: 2.2,
          endScale: 6.5,
          minimumParticleLife: 0.8,
          maximumParticleLife: 1.9,
          minimumSpeed: 6,
          maximumSpeed: 16,
          imageSize: new Cesium.Cartesian2(22, 22),
          emissionRate: 42,
          emitter: new Cesium.CircleEmitter(95),
          modelMatrix,
          updateCallback: (p: Cesium.Particle, dt: number) => {
            p.velocity.z += 26 * dt;
            p.velocity.x += driftX * dt;
            p.velocity.y += driftY * dt;
          },
        }),
      ) as Cesium.ParticleSystem;
      this.smokeParticles = this.viewer.scene.primitives.add(
        new Cesium.ParticleSystem({
          image: smokeParticleImage(),
          startColor: Cesium.Color.fromCssColorString("#7d828a").withAlpha(0.5),
          endColor: Cesium.Color.fromCssColorString("#4a4e55").withAlpha(0.0),
          startScale: 3.2,
          endScale: 13,
          minimumParticleLife: 3.2,
          maximumParticleLife: 6.4,
          minimumSpeed: 9,
          maximumSpeed: 22,
          imageSize: new Cesium.Cartesian2(40, 40),
          emissionRate: 16,
          emitter: new Cesium.CircleEmitter(160),
          modelMatrix,
          updateCallback: (p: Cesium.Particle, dt: number) => {
            p.velocity.z += 14 * dt;
            p.velocity.x += driftX * 2.4 * dt;
            p.velocity.y += driftY * 2.4 * dt;
          },
        }),
      ) as Cesium.ParticleSystem;
    } else {
      this.fireParticles.modelMatrix = modelMatrix;
      this.smokeParticles!.modelMatrix = modelMatrix;
      this.fireParticles.show = true;
      this.smokeParticles!.show = true;
    }
  }

  // ---- routes -------------------------------------------------------------------

  renderRoutes(rec: RouteRecommendation | null, activeId: string | null): void {
    const ents = this.routeDS.entities;
    ents.removeAll();
    if (!rec) return;

    for (const route of rec.candidates) {
      const isActive = route.routeId === activeId;
      if (!isActive) {
        ents.add({
          polyline: this.lineOn(route.polyline, 5, 4,
            new Cesium.PolylineDashMaterialProperty({
              color: COLORS.routeAlt.withAlpha(0.55),
              dashLength: 16,
            })),
        });
      }
    }

    const active = rec.candidates.find((c) => c.routeId === activeId) ?? rec.candidates[0];
    if (!active) return;

    // Glowing blue route.
    ents.add({
      polyline: this.lineOn(active.polyline, 7, 13,
        new Cesium.PolylineGlowMaterialProperty({
          color: COLORS.route.withAlpha(0.95),
          glowPower: 0.22,
          taperPower: 1,
        })),
    });

    // Direction arrows: short arrow segments roughly every 500 m.
    this.addRouteArrows(active);

    // Maneuver markers.
    for (const m of active.maneuvers) {
      if (m.type === "depart") continue;
      const isArrive = m.type === "arrive";
      const sym =
        m.type === "turn_right" ? "➔ RIGHT" :
        m.type === "turn_left" ? "⬅ LEFT" :
        m.type === "uturn" ? "⟲ U-TURN" :
        m.type === "slight_right" ? "↗ BEAR R" :
        m.type === "slight_left" ? "↖ BEAR L" :
        isArrive ? "◈ SAFE ZONE (SIM)" : "↑ CONTINUE";
      ents.add({
        position: groundPosition(m.coordinate[0], m.coordinate[1], 9),
        point: {
          pixelSize: isArrive ? 11 : 8,
          color: isArrive ? COLORS.safe : Cesium.Color.WHITE,
          outlineColor: COLORS.route,
          outlineWidth: 2.5,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        label: {
          text: sym,
          font: "700 11px Inter, sans-serif",
          fillColor: isArrive ? COLORS.safe : Cesium.Color.fromCssColorString("#bfe7ff"),
          outlineColor: Cesium.Color.BLACK.withAlpha(0.92),
          outlineWidth: 3,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cesium.Cartesian2(0, -16),
          distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 14000),
        },
      });
    }
  }

  private addRouteArrows(route: CandidateRoute): void {
    const pts = route.polyline;
    let acc = 0;
    let nextAt = 420;
    for (let i = 1; i < pts.length; i++) {
      acc += haversineM(pts[i - 1], pts[i]);
      if (acc >= nextAt) {
        nextAt += 520;
        const a = pts[Math.max(0, i - 1)];
        const b = pts[i];
        const brg = bearingDeg(a, b);
        const lenLat = 110 / 111320;
        const tip: LonLat = [
          b[0] + Math.sin((brg * Math.PI) / 180) * lenLat * 1.25,
          b[1] + Math.cos((brg * Math.PI) / 180) * lenLat,
        ];
        this.routeDS.entities.add({
          polyline: {
            positions: [groundPosition(a[0], a[1], 9), groundPosition(tip[0], tip[1], 9)],
            width: 9,
            material: new Cesium.PolylineArrowMaterialProperty(
              Cesium.Color.fromCssColorString("#bfe7ff").withAlpha(0.85),
            ),
          },
        });
      }
    }
  }

  // ---- safe zones (dynamic status: the safe zone can MOVE) -------------------------

  renderSafeZones(
    statuses: Array<{ zone: SafeZone; status: string; bufferMinutes: number;
                      insidePredictedZone: boolean; note: string }>,
    activeDestinationId: string | null,
  ): void {
    for (const e of this.safeZoneEntities.values()) this.staticDS.entities.remove(e);
    this.safeZoneEntities.clear();
    for (const s of statuses) {
      const z = s.zone;
      const isActive = z.id === activeDestinationId;
      const color = s.status === "compromised"
        ? Cesium.Color.fromCssColorString("#ff3b30")
        : s.status === "at_risk"
          ? Cesium.Color.fromCssColorString("#ffb020")
          : COLORS.safe;
      const tag = s.status === "compromised" ? "✕ COMPROMISED — "
        : s.status === "at_risk" ? "⚠ MONITORED — " : "◈ ";
      const marker = this.staticDS.entities.add({
        position: groundPosition(z.lon, z.lat, 6),
        point: {
          pixelSize: isActive ? 14 : 10,
          color,
          outlineColor: Cesium.Color.WHITE.withAlpha(0.9),
          outlineWidth: isActive ? 3 : 2,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        label: {
          text: `${tag}${z.name.toUpperCase()}${isActive ? "  ← DESTINATION" : ""}`,
          font: `${isActive ? 700 : 600} 12px Inter, sans-serif`,
          fillColor: color,
          outlineColor: Cesium.Color.BLACK.withAlpha(0.9),
          outlineWidth: 3,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cesium.Cartesian2(0, -18),
          distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 30000),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
      const ring = this.staticDS.entities.add({
        position: groundPosition(z.lon, z.lat, 2),
        ellipse: this.discOn(z.lon, z.lat, isActive ? 200 : 150,
          color.withAlpha(s.status === "compromised" ? 0.10 : 0.16),
          color.withAlpha(0.75)),
      });
      this.safeZoneEntities.set(z.id + "-m", marker);
      this.safeZoneEntities.set(z.id + "-r", ring);
    }
  }

  // ---- reported low-visibility zone ------------------------------------------------

  renderReportedZone(zone: { center: LonLat; radiusM: number } | null): void {
    const ents = this.hazardDS.entities;
    ents.removeAll();
    if (!zone) return;
    const [lon, lat] = zone.center;
    ents.add({
      position: groundPosition(lon, lat, 3),
      ellipse: this.discOn(lon, lat, zone.radiusM,
        new Cesium.StripeMaterialProperty({
          evenColor: Cesium.Color.fromCssColorString("#ff5a1f").withAlpha(0.22),
          oddColor: Cesium.Color.TRANSPARENT,
          repeat: 14,
        }),
        Cesium.Color.fromCssColorString("#ff5a1f").withAlpha(0.85)),
      label: {
        text: "⚠ REPORTED LOW VISIBILITY",
        font: "700 11px Inter, sans-serif",
        fillColor: Cesium.Color.fromCssColorString("#ffb265"),
        outlineColor: Cesium.Color.BLACK.withAlpha(0.92),
        outlineWidth: 3,
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        pixelOffset: new Cesium.Cartesian2(0, -22),
      },
    });
  }

  // ---- user dot ------------------------------------------------------------------

  renderUser(user: UserPosition | null): void {
    if (!user) {
      this.userDS.entities.removeAll();
      this.userEntity = null;
      this.userPos = null;
      return;
    }
    this.userPos = { lon: user.lon, lat: user.lat, heading: user.headingDeg };
    if (!this.userEntity) {
      const posProp = new Cesium.CallbackPositionProperty(
        () => groundPosition(this.userPos!.lon, this.userPos!.lat, 8),
        false,
      );
      this.userEntity = this.userDS.entities.add({
        position: posProp,
        point: {
          pixelSize: 15,
          color: COLORS.user,
          outlineColor: Cesium.Color.WHITE,
          outlineWidth: 3,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        label: {
          text: "SAMPLE RESIDENT · SIM",
          font: "700 11px Inter, sans-serif",
          fillColor: Cesium.Color.fromCssColorString("#dff1ff"),
          outlineColor: Cesium.Color.BLACK.withAlpha(0.92),
          outlineWidth: 3,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cesium.Cartesian2(0, -22),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
      // Pulsing halo as a billboard point: per-frame pixelSize/alpha changes
      // are free (no geometry re-tessellation like a dynamic ellipse).
      this.userDS.entities.add({
        position: posProp,
        point: {
          pixelSize: new Cesium.CallbackProperty(
            () => 26 + 16 * (0.5 + 0.5 * Math.sin(this.pulse * 2.4)),
            false,
          ),
          color: new Cesium.CallbackProperty(
            () => COLORS.user.withAlpha(0.22 - 0.10 * (0.5 + 0.5 * Math.sin(this.pulse * 2.4))),
            false,
          ),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
    }
  }

  destroy(): void {
    this.destroyed = true;
    try {
      this.viewer?.destroy();
    } catch {
      /* already gone */
    }
  }
}

export const sceneManager = new SceneManager();
