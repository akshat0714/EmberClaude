# Safety positioning & limitations

**Read this before demoing or extending the project.**

## What this application is

A **historical simulation and future wildfire decision-support prototype**. It replays a synthetic approximation of the January 7, 2025 Palisades Fire and demonstrates how simulation-backed routing and voice guidance *could* assist evacuation planning and preparedness training.

## What this application is NOT

* ❌ Not a real-time emergency service.
* ❌ Not a source of evacuation instructions during an actual emergency.
* ❌ Not survey-accurate geography, parcel data, or an official fire reconstruction.
* ❌ Not a guarantee of safety under any circumstances.

## Non-negotiable product rules

1. Every screen carries the banner: *“Simulation only. Follow official evacuation orders and emergency personnel.”*
2. Every assistant response ends with an official-guidance deferral; phrasing like “guaranteed safe”, “exact safe route”, “ignore officials”, “this will definitely save you” is **banned and test-enforced** (`backend/tests/test_guidance.py`).
3. Approved vocabulary: *recommended simulated route · modeled risk · confidence score · based on current scenario inputs · simulated lower-risk zone*.
4. The app presents the **lowest modeled-risk route under current scenario inputs** — explicitly not a guaranteed safe route; the “Why this route?” panel restates this.
5. Officially closed roads are hard-excluded from routing (compliance is part of the score), and the assistant says “do not drive around barricades.”

## Data honesty

Every file in `data/demo/` carries a disclaimer field marking it **SYNTHETIC DEMO DATA**. Ignition area/time, wind regime, road names/topology and the evacuation-center reference approximate public reporting; geometry, buildings, vegetation, fire timing, smoke and travel times are generated. Sources of truth for the labeling: `source: historical_demo|predicted` on fire cells, `approximate: true` on roads, `synthetic: true` on buildings/vegetation.

## Model limitations (v1)

| Area | Limitation |
|---|---|
| Fire | Demo-grade spread formula; scripted spotting; single wind vector; no fuel moisture, suppression, or structure-to-structure ignition |
| Smoke | Geometric plumes, not dispersion physics (no HYSPLIT/WRF) |
| Terrain | Analytic heightfield shaped like — but not equal to — the real topography |
| Roads | ~30-edge demo graph; no lane counts, signals, contraflow, or real congestion feeds |
| Traffic | Static congestion factors + time ramp; no microsimulation (SUMO planned) |
| People | One simulated resident; profiles are illustrative |
| Guidance | Rule-based templates; no NLU beyond regex intents |
| Sessions | Single in-memory scenario; no auth/persistence |

## Ethical notes

The Palisades Fire was a real disaster in which people died and thousands lost their homes. The demo treats it as a *case study for preparedness technology*: it avoids depicting casualties, names no real individuals, marks all synthetic layers, and frames every capability as decision support subordinate to official emergency management.
