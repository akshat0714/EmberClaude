# Judge demo script

One click — **▶ RUN JUDGE DEMO** (left panel) — plays the full story in ~3 minutes. Pacing/captions/voice come from `data/demo/judge_demo_script.json`; every spatial beat calls the live APIs (nothing is canned).

| # | Step | What the judge sees / hears |
|---|---|---|
| 1 | `intro` — camera flies from offshore into the Palisades twin | Voice: “simulation-backed replay… follow official evacuation orders.” |
| 2 | `ignite` — minute 0 at the ridge above Piedra Morada Dr | First fire cells pulse; ignition label visible |
| 3 | `spread` — replay advances to minute 16 | Front runs SSW under 38 mph NNE wind; smoke plumes drift downwind; risk rings + dotted uncertainty envelope expand |
| 4 | `placeUser` — blue dot appears on Palisades Drive | Caption: inside the 30-minute modeled spread envelope |
| 5 | `ask` — resident asks **“Where do I go?”** | Assistant answers with first maneuvers, modeled buffer, confidence + official-orders line |
| 6 | `compare` — 3 candidate cards | fastest / lowest smoke / largest fire buffer with time·buffer·smoke·score |
| 7 | `select` — recommended route glows blue | Voice: “…not the fastest descent — the quickest option leaves only a few modeled minutes of fire buffer; the selected route roughly doubles it.” |
| 8 | `drive1` — chase-cam follows the dot; turn-by-turn callouts | “In 300 feet, turn right onto Sunset Boulevard.” → “Turn right… now.” Fire keeps spreading during the drive |
| 9 | `visibility` — resident: **“No, I can't see ahead. It's bright orange.”** | Hatched “REPORTED LOW VISIBILITY” zone appears ahead; smoke re-weighted; **blue path flips** (U-turn to the alternate canyon); assistant explains |
| 10 | `drive2` → `arrive` — updated route to the Santa Monica staging area | “You have reached the simulated lower-risk zone. Continue to follow official emergency guidance.” |
| 11 | `summary` — judge panel | ✓ fire predicted ✓ route adapted ✓ voice guidance ✓ high-risk zone avoided ✓ official-order guardrail preserved + Export JSON |

## Operating tips

* Chrome on a Mac gives the best voice; click once anywhere if the first utterance is silent (autoplay policy), or use 🔊 toggle.
* **Stop** any time via the floating Judge-Demo pill (✕) or the left-panel button; the app returns to manual control.
* Great manual follow-ups for Q&A: toggle a road closure mid-route; drag wind direction and watch the plume + routes recompute; press “Missed turn”; ask “What if I missed the turn?” (hypothetical answer, no state change).
* The summary modal's **Export scenario JSON** downloads the full run (params, routes, transcript) for inspection.
