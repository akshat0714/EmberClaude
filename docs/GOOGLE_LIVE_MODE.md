# Live mode — real Google Maps data

One environment variable flips the app from the synthetic twin to a **live digital twin of the real Pacific Palisades**:

```bash
cd backend
cp .env.example .env     # paste your key into GOOGLE_MAPS_API_KEY=...
# restart uvicorn, hard-refresh the browser
```

| Capability | Source | Where it flows |
|---|---|---|
| Photorealistic 3D world (real terrain, buildings, vegetation) | **Google Map Tiles API** (Photorealistic 3D Tiles) rendered through Cesium's native 3D Tiles support | `SceneManager.init` — globe hidden, tiles become the world; fire/route/risk overlays drape onto them via `ClassificationType.BOTH` |
| Real driving directions ("Turn right onto W Sunset Blvd"), alternatives, distances, durations | **Google Routes API** (`computeRoutes`, alternatives on) | `route_engine.recommend_routes_google` — every alternative is hazard-scored by the same FinalRouteScore formula; instructions come verbatim from Google steps |
| Real terrain elevations for the fire model's slope term + entity heights | **Google Elevation API** (one ~150 m grid over the scenario, cached at `data/cache/google_elevation_grid.json`) | `google_maps.elevation_grid` → backend slope function + `GET /terrain/grid` → frontend height lookups |
| Real current wind (speed/direction/gusts) | **Open-Meteo** (keyless, free) | left panel **Use live wind** → fire + smoke re-simulate |

## How a person experiences it

1. The resident (blue dot) sits on Palisades Drive inside the modeled risk envelope — or press **⊕ Start from my location** (browser geolocation; must be inside the scenario bounds).
2. "Where do I go?" returns **live Google directions to the nearest viable safe zone**, hazard-scored against the fire prediction; the assistant reads real road names.
3. The fire keeps expanding (wind + real-terrain slope). Every advance re-checks the safe zones against the **predicted spread zone** (perimeter at t+30 min plus arrival buffers).
4. When the predicted zone encroaches on the destination, the **safe zone MOVES**: the backend relocates to the next viable zone, re-plans with Google directions from the person's live position, the marker turns red/✕, and the assistant announces: *"…is now inside the modeled predicted spread zone. Redirecting to … and re-routing."*

## Honest constraints

* Google can't route *around* arbitrary polygons. The engine requests alternatives and scores them against fire/smoke/report hazards; if every alternative crosses the modeled front it picks the least-bad and warns. Safe-zone relocation usually resolves the conflict (the destination itself moves away from the prediction).
* Official-closure toggles are enforced in scoring by snapping Google polylines onto the closure-tagged demo graph (same streets) — approximate by design.
* Traffic: `TRAFFIC_UNAWARE` requests plus a modeled evacuation-congestion factor. Switch to `TRAFFIC_AWARE` in `google_maps.compute_routes` if your billing tier allows.
* Fuel load is still the synthetic vegetation map (LANDFIRE is the upgrade path); slope and wind are real in live mode.
* Any Google failure (quota, offline, bad key) degrades to the synthetic twin **mid-session** without breaking the demo; the UI badge and route cards always show which source produced the current plan.

## Cost guardrails

Photorealistic tiles, Routes and Elevation all sit inside Google's monthly free tier at demo volumes (the elevation grid is fetched once and cached). Restrict the key by referrer, set per-API quotas, and never commit `.env`.
