# Fire model

`backend/app/fire_model.py` — an **explainable cellular spread model**, deterministic, calibrated to *feel* like the explosive first hour of the Jan 7, 2025 Palisades Fire. It is demo-grade by design and structured to be replaced by Rothermel/FARSITE-class physics later.

## Representation

The fire is an **array of `FireCell`s** on an irregular ~115 m lattice — never a growing circle. Each cell records `lat/lon`, `radiusMeters`, `ignitionMinute`, `intensity`, `confidence`, `source` (`historical_demo | predicted | observed`), `fuelLoad`, `slopeFactor`, `windAlignment`, `spreadRateMetersPerMinute`.

Seeds: a 3-cell cluster at the documented ignition area (~Piedra Morada Dr, 10:30 AM) plus two scripted **spot-fire ignitions** approximating wind-driven ember jumps (ridge flank at minute 8, Rustic Canyon brush at minute 12). Spotting is what made the real event so fast; here it is scripted and labeled synthetic.

## Spread algorithm (fast marching)

Every burning cell offers ignition to its 16 compass neighbors at step Δ=145 m; a priority queue keeps the *earliest offered ignition time* per lattice cell (lazy Dijkstra). For a neighbor at bearing **B**:

```
rate (m/min) = BASE_RATE                      # 9 m/min
             × windMult                       # 0.55 + 1.25·(wind_mph/40)
             × alignMult(B)                   # downwind ≤2.15×, crosswind ~0.55×, upwind ≥0.18×
             × fuelMult                       # 0.30 + 1.10·fuelLoad   (0 over water → fire stops)
             × slopeMult                      # clamp(1 + 2.4·grade, 0.5, 1.9)  — fire runs uphill
             × intensityMult                  # 0.55 + 0.65·intensity dial
             × jitter                         # 0.85 + 0.30·hash(cell)  → ragged organic fronts

delay = Δ / rate          ignition(neighbor) = ignition(parent) + delay
confidence(neighbor) = confidence(parent) · e^(−delay/130)     (drop below 0.12 → prune)
```

`alignMult` uses cos θ between the spread bearing and the downwind direction: `0.55 + 1.60·cosθ^1.8` downwind, floored at 0.18 upwind — this is what the *“spread moves more strongly downwind”* test pins.

Cell intensity over time: 2-min ramp-up → ~22 min full burn → exponential decay (τ=30 min), scaled by fuel and wind alignment.

## Derived per-minute layers (every 5 min, 0–75)

* **`firePerimeterByMinute`** — angular sweep around the intensity-weighted centroid (56 bins, max reach per bin, gap interpolation, double smoothing) → irregular star-shaped polygon; area via shoelace.
* **`smokeZonesByMinute`** — a 3-level nested main plume (heavy/moderate/light) from the centroid plus up to 7 flank plumes from spatially-distinct strong emitters. Plume = downwind cone with ragged edges; length grows with wind and elapsed time. Served as *separate translucent polygons* (overlap reads as density — no union math needed).
* **`riskZonesByMinute`** — extreme = current perimeter +180 m; high = predicted perimeter at t+15; elevated = predicted at t+30 plus the heavy-smoke corridor.
* **`uncertaintyEnvelopeByMinute`** — predicted t+15 perimeter pushed outward (dotted in UI).
* **`predictedFireCellsByMinute`** — cells igniting within the next 20 min (dim/ringed in UI).

## Fire-arrival estimate (used by routing)

`fire_arrival_minute(p) = min over cells ( ignition_i + dist_i / directionalRate_i )`, where the rate respects the **destination's fuel** (`min(cell fuel, dest fuel)`) so irrigated suburbs buy real minutes and water is unreachable — keeping the estimate consistent with the lattice simulation.

## Honesty model

With default scenario inputs the replay layer is tagged `historical_demo` (synthetic approximation of public reporting). Change any dial (wind/intensity) and outputs become `predicted`. Confidence shown in the UI additionally decays with how far past the time cursor an ignition lies.

## Known simplifications

No spotting *model* (scripted jumps only), no fuel moisture/weather time series, no suppression, single wind vector per run, plume geometry instead of dispersion physics. See `docs/DATA_SOURCES_TO_ADD_LATER.md` for the upgrade path.
