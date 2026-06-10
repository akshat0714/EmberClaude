# Route model

`backend/app/route_engine.py` — **time-aware, hazard-aware routing**, not shortest-path.

## Network

A hand-laid demo graph of the real Palisades topology (Sunset Blvd, Palisades Dr, Temescal Canyon Rd, Chautauqua Blvd, PCH, San Vicente corridor) with curved per-edge geometry shared verbatim by routing and rendering, per-edge class/speed/congestion and closure groups. Labeled approximate — never for navigation. Arbitrary user positions are connected via nearest-edge snapping; doubling back against the user's heading pays an explicit U-turn penalty (so "turn around when safe" is possible but never chosen lightly).

## Edge cost at entry time *t*

Each edge is sampled every ~120 m and evaluated **at the minute the driver would actually be there**:

```
traverse = length / speed × congestion(t) × smokeSlowdown
  congestion(t)   = 1 + edgeCongestion·(0.35 + 0.65·min(1, t/60))   # evacuation traffic builds
  smokeSlowdown   = 1 + 0.35·smoke   (×1.5·smoke once visibility is lost — you crawl in smoke)

penalties:
  fire     : +1e6 if min over samples of (fireArrival − passTime) < 1.5 min   # never route through fire
  buffer   : +w_b·60·shortfall^1.6 when the modeled buffer is under the profile target
  smoke    : +w_s·smokeScale(profile)·avgSmoke·traverse
  closure  : +1e9 for officially closed groups (hard compliance)
  report   : +200 per edge inside a user-reported zero-visibility zone (≈ near-closed)
```

Smoke at a sample = max density of any plume polygon containing it, raised by the person profile's `smokeSensitivity`, user `smokeSensitivityBoost`, the reported-zone disc (density 0.95, r=340 m) and a ×1.6 visibility-lost factor.

## Three genuinely different candidates

Dijkstra runs under three weight profiles — *fastest*, *lowest smoke*, *largest fire buffer*. If profiles converge on one corridor, the duplicate replans with every previously-used edge penalized until a distinct alternative emerges. Labels are then **re-assigned by measured metrics** (quickest measured time gets "Fastest route", etc.) so the comparison cards never lie.

## FinalRouteScore (the spec formula)

```
FinalRouteScore = 0.30·fireBufferScore          # clamp(bufferMin / 45)
                + 0.25·smokeAvoidanceScore      # 1 − smokeExposure/100
                + 0.15·travelTimeScore          # fastestTime / ownTime
                + 0.10·roadClosureComplianceScore
                + 0.10·profileSuitabilityScore  # maneuvers + canyon share vs mobility
                + 0.05·congestionScore
                + 0.05·backupRouteScore         # corridor diversity vs alternatives
```

Highest score wins. Each `CandidateRoute` carries the full sub-score vector, distance, modeled travel time, `fireArrivalBufferMinutes` (min over samples of arrival − passTime), `smokeExposureScore` (0–100), congestion/closure risks, accessibility, confidence and human-readable warnings.

## Maneuvers

Edges are grouped into same-road runs; transitions emit typed maneuvers (`depart/continue/slight/turn/uturn/arrive`) with distances in feet/miles — e.g. *“In 300 feet, turn right onto Chautauqua Boulevard.”* The origin link inherits the snapped road's real name so re-routes mid-block read naturally, and a heading reversal injects *“Make a U-turn when safe…”*.

## Explanations

`explanation` and `whyNotFastest` are generated from the actual numbers (time delta, smoke delta, buffer delta, closure context) and always end on the official-orders reminder. The guidance layer quotes these — it never invents its own.

## Re-routing triggers

* user deviates / **missed turn** → snap from new position, replan
* **visibility lost** → report disc ahead of user + global smoke re-weighting + smoke slowdown
* **road blocked** → report disc as near-closure
* **official closure toggles** → hard exclusion
