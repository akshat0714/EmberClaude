# Voice assistant

Two halves: a backend **GuidanceBrain** (what to say) and a browser **speech layer** (how to say/hear it).

## GuidanceBrain (`backend/app/guidance.py`)

Rule-based v1 — ordered regex intent matching, first match wins:

| Intent | Example trigger | Effect |
|---|---|---|
| `where_do_i_go` | "Where do I go?" | compute/refresh recommendation, read first maneuvers + buffer + confidence |
| `visibility_lost` | "I can't see ahead… bright orange" | mark report disc ahead, re-weight smoke, **re-route**, explain |
| `missed_turn` | "I missed the turn" | deviate past junction, **re-route from live position** |
| `road_blocked` | "the road looks blocked" | near-closure disc ahead, **re-route**, "do not drive around barricades" |
| `repeat` | "repeat that" | restate current instruction + remaining distance + buffer |
| `am_i_safe` | "am I safe yet?" | arrival check + modeled buffer, never "yes, safe" |
| `keep_going` | "should I keep going?" | re-validate route; re-route if the buffer tightened |
| `hypothetical_missed_turn` | "what if I miss the turn?" | explains re-route behavior without changing state |
| `status` | "status" | scenario minute, active cells, wind, route summary |
| `general` | anything else | capabilities + safety line |

### Guardrails (enforced by tests)

* **Never invents geometry** — every road name/distance is read from route-engine maneuvers (`test_guidance_only_reads_engine_maneuvers`).
* **Never promises safety** — banned phrasing ("guaranteed safe", "exact safe route", "ignore officials", "definitely save") is structurally absent (`test_guidance_never_promises_guaranteed_safety`).
* **Always defers** — every response and `safetyReminder` contains an official-guidance reference (`test_every_response_defers_to_official_guidance`). Vocabulary: *recommended simulated route, modeled risk, confidence, based on current scenario inputs*.

### Swapping in a real LLM later

`respond(GuidanceRequest, state) -> GuidanceResponse` is the whole contract. An LLM would be allowed only to *paraphrase* the same engine-produced facts (maneuvers, metrics, warnings), with the banned-phrase test still applied to its output. No API key is required in v1.

## Browser speech (`frontend/src/lib/speech.ts`)

* **Synthesis**: `window.speechSynthesis`, calm en-US voice preference (Samantha/Google US English/Aria), rate 1.04, interruptible for urgent re-routes. Mutable from the top bar.
* **Recognition**: one-shot push-to-talk on `webkitSpeechRecognition` when present (Chrome/Edge). Otherwise the 🎙 button disables itself and users rely on typed input + quick-action chips — full feature parity.
* **Turn-by-turn callouts** are produced client-side by the demo director from `AdvanceResult.nextManeuver` only: pre-announce under 320 m ("In 300 feet, …"), execute under 75 m ("Turn right now.").
