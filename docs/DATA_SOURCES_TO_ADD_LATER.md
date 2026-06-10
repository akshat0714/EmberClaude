# Data sources to add later

v1 runs entirely on deterministic synthetic data behind clean interfaces. Each integration below replaces one lookup or one generator — the API contracts (`FireCell`, byMinute frames, road graph edges, `CandidateRoute`) stay unchanged.

| Source | Replaces | Integration point | Notes |
|---|---|---|---|
| **NASA FIRMS** (VIIRS/MODIS hotspots) | seed/observed fire cells | `fire_model.simulate_cells` seeds; cells tagged `observed` | Free API key; 375 m VIIRS detections map naturally onto the cell lattice |
| **CAL FIRE / NIFC incident perimeters** | replay perimeters & validation | serve alongside model output in `firePerimeterByMinute` | GeoJSON feeds (WFIGS); also powers honest "observed vs modeled" overlays |
| ✅ **Google Routes API** (done, live mode) | demo routing | `route_engine.recommend_routes_google` | OSMnx local graph still valuable for offline/custom cost routing |
| ✅ **Open-Meteo live wind** (done) | wind sliders | left-panel **Use live wind** → `/weather/live` | NOAA/RAWS hourly *time series* per step remains future work |
| **LANDFIRE FBFM40 fuel models** | `VEGETATION_ZONES`/`fuel_at` | raster sampler behind `fuel_at(lon, lat)` | Direct drop-in: the model only asks for 0..1 fuel load |
| ✅ **Google Elevation API** (done, live mode) | analytic terrain | cached grid feeds backend slope + frontend heights | USGS 3DEP remains a keyless alternative |
| ✅ **Google Photorealistic 3D Tiles** (done, live mode) | generated buildings + terrain visuals | Cesium 3D Tiles primitive | OSM footprints remain useful for analytics on structures |
| **SUMO traffic microsimulation** | congestion factors | per-edge time-dependent travel times feeding `_congestion_factor` | Enables contraflow and gridlock studies (the real event's pain point) |
| **HYSPLIT / WRF-SFIRE smoke** | geometric plumes | `smokeZonesByMinute` frames + `smoke_density_at` | Same polygon-frame contract |
| **Real LLM (e.g. Claude)** | template phrasing in GuidanceBrain | behind `guidance.respond`; engine facts only; banned-phrase test stays | No geometry generation allowed — narration only |

## Suggested order of attack

1. OSMnx road graph (biggest realism win, pure swap)
2. USGS 3DEP terrain + LANDFIRE fuels (makes slope/fuel terms real)
3. NOAA wind time series (hourly shifts)
4. FIRMS + CAL FIRE overlays (observed vs modeled honesty)
5. SUMO congestion, then smoke physics, then LLM narration
