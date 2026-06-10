# Palisades Fire 3D Escape Twin

**A hyperrealistic browser-based 3D wildfire evacuation digital twin**, modeled on the January 7, 2025 Palisades Fire. One simulated resident, a live cellular fire-spread model, time-aware hazard-aware routing, and a calm voice assistant that re-plans the escape route as conditions change.

> ⚠️ **Simulation only.** Every route, fire cell, smoke plume and instruction in this app is *modeled demo data*. In any real emergency: **follow official evacuation orders and emergency personnel, and never enter closed roads.** The app recommends the *lowest modeled-risk route under current scenario inputs* — never a guaranteed safe route.

![architecture](docs/ARCHITECTURE.md)

---

## What the demo shows

1. A 3D Pacific Palisades / Santa Monica Mountains scene (synthetic terrain matched to the real topography pattern, extruded buildings, named roads, fuel zones).
2. The fire replayed as an **array of fire cells** spreading minute-by-minute under NNE Santa Ana wind — irregular perimeter, downwind smoke plumes, expanding risk rings, dotted uncertainty envelope.
3. A bright **blue dot** (Sample Resident) placed inside the modeled risk envelope in the Palisades Highlands.
4. Three scored candidate routes (**fastest / lowest smoke / largest fire buffer**) and a glowing **blue evacuation path** that re-plans live.
5. A **voice assistant** (browser speech synthesis + optional push-to-talk) that answers "Where do I go?", "I can't see ahead — it's bright orange", "I missed the turn", "Am I safe yet?" — quoting only the route engine's maneuvers.
6. Turn-by-turn callouts ("In 300 feet, turn right…", "Turn right now", "Re-routing based on your current position").
7. **Judge Demo Mode** — one button replays the entire emergency story automatically (~3 minutes).

## Quick start (macOS)

Prereqs: **Python 3.11+**, **Node 18+** (`brew install python node` if needed). Two terminals.

**Terminal 1 — backend (FastAPI, port 8000):**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — frontend (Vite, port 5173):**

```bash
cd frontend
npm install
npm run dev
```

Then open **http://localhost:5173** in Chrome (best voice support) and press **▶ RUN JUDGE DEMO**.

### 🔑 LIVE MODE — real Google Maps data (recommended)

```bash
cd backend && cp .env.example .env   # paste your Google Maps API key, restart uvicorn
```

One key (Map Tiles API + Routes API + Elevation API enabled) switches the app to **Google Photorealistic 3D Tiles of the real Palisades, real Google driving directions, and real terrain elevations** feeding the fire model — with the safe zone automatically *relocating* (and re-routing via Google) whenever the predicted spread zone encroaches on it. Live wind via Open-Meteo needs no key. Full guide: `docs/GOOGLE_LIVE_MODE.md`. Without a key everything still runs on the synthetic twin.

### Regenerate the demo dataset (optional)

```bash
cd backend && source .venv/bin/activate
python -m scripts.generate_demo_data
```

Deterministic: re-running always produces identical files in `data/demo/`.

### Run the tests

```bash
# backend (15 tests: wind physics, closures, re-routes, safety guardrails)
cd backend && source .venv/bin/activate && pytest

# frontend (typecheck + build + render smoke tests)
cd frontend && npm run typecheck && npm run build && npm test
```

## Troubleshooting (macOS)

| Symptom | Fix |
|---|---|
| Loading screen says "is the backend running?" | Start Terminal 1; check `curl http://127.0.0.1:8000/health` |
| Port 8000 busy | `lsof -ti :8000 \| xargs kill`, or run uvicorn with `--port 8001` and `VITE_API_BASE=http://127.0.0.1:8001 npm run dev` |
| Port 5173 busy | `npm run dev -- --port 5174` |
| No voice output | macOS Chrome/Safari ship voices by default; check the 🔊 toggle in the top bar and system volume. First utterance may need one click on the page (autoplay policy). |
| Push-to-talk 🎙 greyed out | Speech *recognition* needs Chrome/Edge; typed commands and quick-action chips always work. |
| Basemap tiles missing (offline) | The app automatically falls back to Cesium's bundled offline NaturalEarth imagery; all simulation layers still render. |
| `pip install` SSL errors on old macOS | `python3 -m pip install --upgrade pip certifi` inside the venv |
| Sluggish 3D | Close other GPU-heavy tabs; toggle off Buildings/Fuel zones in the left panel. |

## Repository layout

```
backend/    FastAPI app: fire model, route engine, guidance brain, tests
frontend/   Vite + React + TypeScript + CesiumJS ops console
data/demo/  Deterministic synthetic dataset (clearly disclaimed)
docs/       Architecture, models, safety, judge script, data roadmap
```

## What is real vs simulated

| Element | Twin mode (no key) | Live mode (`GOOGLE_MAPS_API_KEY`) |
|---|---|---|
| 3D world | Synthetic terrain + generated buildings | **Real** — Google Photorealistic 3D Tiles |
| Terrain heights / fire-slope | Analytic heightfield | **Real** — Google Elevation API grid |
| Driving directions & travel times | Demo road graph | **Real** — Google Routes API (live road names/instructions) |
| Wind | Scenario dials | **Real** option — Open-Meteo current wind (keyless) |
| Fire spread, smoke, risk, predicted zone | Modeled (demo-grade, explainable) | Modeled (same engine, real slope+wind inputs) |
| Fuel/vegetation map | Synthetic | Synthetic (LANDFIRE is the upgrade path) |
| Evacuation guidance | Modeled decision support — **never** official instructions | Same guardrails |

See `docs/SAFETY_AND_LIMITATIONS.md` (read this first) and `docs/DATA_SOURCES_TO_ADD_LATER.md` for the path to real data (NASA FIRMS, CAL FIRE, OSM/OSMnx, NOAA, LANDFIRE, USGS 3DEP, SUMO).

## License / intent

Hackathon prototype for wildfire-preparedness research and demos. Not an emergency service.
