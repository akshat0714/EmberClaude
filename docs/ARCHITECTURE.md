# Architecture

```
┌────────────────────────── Browser (http://localhost:5173) ──────────────────────────┐
│  React + TypeScript + Tailwind (dark EOC theme)                                      │
│                                                                                      │
│  TopBar ── safety banner                    RightPanel ── transcript / status /      │
│  LeftPanel ── scenario dials, closures,                   route cards / "why?"       │
│              layers, JUDGE DEMO            TimelineBar ── replay clock + events      │
│                                                                                      │
│  CesiumScene ⇆ SceneManager (imperative)   director.ts ── judge-demo state machine   │
│      │  CustomHeightmapTerrainProvider      speech.ts ──  Web Speech synth + PTT     │
│      │  (analytic Palisades heightfield)                                             │
│      └─ layers: roads · buildings · fuel · fire cells · perimeters · smoke ·         │
│                 risk rings · uncertainty · routes · user dot · report zone           │
│                                                                                      │
│  zustand store  ←──────────── typed fetch client ────────────→  FastAPI (:8000)      │
└──────────────────────────────────────────────────────────────────────────────────────┘
                                                                     │
        ┌────────────────────────────── Backend ─────────────────────┴──────────────┐
        │ app/main.py        endpoints + CORS + /data static mount                  │
        │ app/state.py       single in-memory scenario session                      │
        │ app/fire_model.py  cellular fast-marching spread, plumes, risk, envelope  │
        │ app/route_engine.py time-aware hazard-aware Dijkstra + FinalRouteScore    │
        │ app/guidance.py    GuidanceBrain (rule intents, guardrailed templates)    │
        │ app/demo_world.py  road graph, fuel zones, buildings, profiles, shelters  │
        │ app/geo.py         geodesy + the shared synthetic terrain formula         │
        │ scripts/generate_demo_data.py → data/demo/*.json (deterministic)          │
        └────────────────────────────────────────────────────────────────────────────┘
```

## Key decisions

**One terrain formula, two implementations.** `backend/app/geo.py::terrain_height_m` and `frontend/src/lib/terrain.ts::terrainHeightM` are the same analytic function (coastal terrace → village mesa → N20°E canyon ridges to ~480 m). The frontend feeds it to Cesium's `CustomHeightmapTerrainProvider`; the backend uses it for slope-dependent fire spread. Result: zero terrain services, zero tokens, and entities never float — at the cost of synthetic (clearly disclaimed) topography. Swapping in USGS 3DEP later only requires replacing both lookups with a raster sampler.

**No Cesium Ion / no API keys required — but one key unlocks LIVE MODE.** Default imagery = CARTO dark basemap (keyless) with automatic fallback to Cesium's bundled offline NaturalEarthII. With `GOOGLE_MAPS_API_KEY` set, the scene swaps to **Google Photorealistic 3D Tiles** of the real Palisades, routing swaps to the **Google Routes API**, terrain swaps to a cached **Google Elevation** grid, and live wind comes from keyless Open-Meteo — all behind the same models and endpoints, with automatic mid-session fallback if Google is unreachable (`docs/GOOGLE_LIVE_MODE.md`). The dynamic safe-zone watcher (`app/safe_zones.py` + `state._watch_safe_zone`) re-evaluates every zone against the predicted spread on each advance and relocates the destination + re-plans when encroached.

**deck.gl evaluated, skipped in v1.** deck.gl has no maintained Cesium interop (it targets MapLibre/Google Maps); double-rendering a second WebGL context and syncing cameras adds risk without adding capability, since Cesium natively handles 3D extrusions, ground-draped polygons, glow polylines and particle systems used here. The overlay data contracts (GeoJSON-ish byMinute frames) are renderer-agnostic, so a deck.gl/MapLibre 2.5D fallback could be added later without backend changes.

**Backend owns all geometry; the brain only narrates.** The GuidanceBrain never fabricates spatial facts — it formats maneuvers/metrics produced by the route engine (enforced by `test_guidance_only_reads_engine_maneuvers`). An LLM can later replace the template layer behind the same `respond()` contract with the same constraint.

**Single demo session.** `app/state.py` holds one scenario (user, conditions, cached sim). Multi-session support = swap the singleton for a session-keyed store; endpoints already take a `sessionId` in the guidance request.

**Determinism everywhere.** No RNG state: hash-noise from lattice coordinates (fire jitter, building variation), fixed seeds in the generator. Identical inputs → identical fire, routes, and demo — essential for a judged demo and for tests.

## Data flow during the judge demo

1. `director.ts` reads `data/demo/judge_demo_script.json` (pacing/captions/voice only).
2. Every spatial beat calls the **live** API: `/simulation/run`, `/guidance/respond`, `/user/advance` — nothing is canned client-side.
3. Store updates → `CesiumScene` effects → `SceneManager` mutates entity layers.
4. Voice lines = `GuidanceResponse.speechText` via Web Speech synthesis.
