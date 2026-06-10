/** Small geodesy helpers shared by the scene and the demo director. */

import type { LonLat } from "../types";

const R = 6_371_000;

export function haversineM(a: LonLat, b: LonLat): number {
  const p1 = (a[1] * Math.PI) / 180;
  const p2 = (b[1] * Math.PI) / 180;
  const dp = p2 - p1;
  const dl = ((b[0] - a[0]) * Math.PI) / 180;
  const s = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
}

export function bearingDeg(a: LonLat, b: LonLat): number {
  const p1 = (a[1] * Math.PI) / 180;
  const p2 = (b[1] * Math.PI) / 180;
  const dl = ((b[0] - a[0]) * Math.PI) / 180;
  const x = Math.sin(dl) * Math.cos(p2);
  const y = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl);
  return ((Math.atan2(x, y) * 180) / Math.PI + 360) % 360;
}

export function polylineLengthM(coords: LonLat[]): number {
  let total = 0;
  for (let i = 0; i < coords.length - 1; i++) total += haversineM(coords[i], coords[i + 1]);
  return total;
}

export function metersToFeetLabel(m: number): string {
  const feet = m * 3.28084;
  if (feet < 1000) return `${Math.max(50, Math.round(feet / 50) * 50)} ft`;
  return `${(m / 1609.34).toFixed(1)} mi`;
}

export function fmtMiles(m: number): string {
  return `${(m / 1609.34).toFixed(1)} mi`;
}
