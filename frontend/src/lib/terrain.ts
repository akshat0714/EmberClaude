/**
 * Synthetic Palisades terrain — EXACT mirror of backend/app/geo.py.
 *
 * One analytic heightfield drives everything: Cesium's terrain provider,
 * building base heights, fire-cell elevations and the camera floor. Keep the
 * constants in sync with the Python implementation (documented in
 * docs/ARCHITECTURE.md) so the 3D world and the physics agree without any
 * terrain service or API token.
 */

import * as Cesium from "cesium";

export const M_PER_DEG_LAT = 111_320.0;
export const REF_LON = -118.53;
export const REF_LAT = 34.04;

const COAST_REF_LON = -118.498;
const COAST_LAT_AT_REF = 34.008;
const COAST_SLOPE = -0.55;

export function mPerDegLon(lat = REF_LAT): number {
  return M_PER_DEG_LAT * Math.cos((lat * Math.PI) / 180);
}

export function coastLat(lon: number): number {
  return COAST_LAT_AT_REF + COAST_SLOPE * (lon - COAST_REF_LON);
}

function smoothstep(t: number): number {
  const x = Math.max(0, Math.min(1, t));
  return x * x * (3 - 2 * x);
}

/** Ground height in meters at a lon/lat — same formula as the backend. */
export function terrainHeightM(lon: number, lat: number): number {
  const dCoast = (lat - coastLat(lon)) * M_PER_DEG_LAT;
  if (dCoast <= 0) return -30;

  const x = (lon - REF_LON) * mPerDegLon();
  const y = (lat - REF_LAT) * M_PER_DEG_LAT;
  const inland = smoothstep(dCoast / 5500);

  const a = (20 * Math.PI) / 180;
  const c = x * Math.cos(a) - y * Math.sin(a);
  const along = x * Math.sin(a) + y * Math.cos(a);
  const ridge =
    0.55 * Math.sin(c / 430) +
    0.3 * Math.sin(c / 187 + 1.7) +
    0.15 * Math.sin(c / 921 + 0.6) +
    0.18 * Math.sin(along / 640 + c / 510);
  const ridgeN = Math.max(0, Math.min(1, 0.5 + (0.5 * ridge) / 1.18));

  let h = inland * (90 + 380 * ridgeN * inland);

  const mesa = Math.exp(-(((lon + 118.522) / 0.011) ** 2) - ((lat - 34.041) / 0.0075) ** 2);
  h = h * (1 - 0.8 * mesa) + (50 + dCoast * 0.006) * (0.8 * mesa);

  if (dCoast < 260) h = Math.min(h, 6 + dCoast * 0.05);
  return h;
}

/** Cesium terrain provider sampling the analytic heightfield. */
export function createTwinTerrainProvider(): Cesium.CustomHeightmapTerrainProvider {
  const width = 32;
  const height = 32;
  const tilingScheme = new Cesium.GeographicTilingScheme();
  return new Cesium.CustomHeightmapTerrainProvider({
    width,
    height,
    tilingScheme,
    callback: (x: number, y: number, level: number) => {
      const rect = tilingScheme.tileXYToRectangle(x, y, level);
      const buffer = new Float32Array(width * height);
      for (let row = 0; row < height; row++) {
        const lat = Cesium.Math.toDegrees(
          rect.north - (rect.north - rect.south) * (row / (height - 1)),
        );
        for (let col = 0; col < width; col++) {
          const lon = Cesium.Math.toDegrees(
            rect.west + (rect.east - rect.west) * (col / (width - 1)),
          );
          buffer[row * width + col] = Math.max(terrainHeightM(lon, lat), -30);
        }
      }
      return buffer;
    },
  });
}

/** Cartesian3 on (or offset above) the synthetic ground. */
export function groundPosition(lon: number, lat: number, offsetM = 0): Cesium.Cartesian3 {
  return Cesium.Cartesian3.fromDegrees(lon, lat, Math.max(terrainHeightM(lon, lat), 0) + offsetM);
}
