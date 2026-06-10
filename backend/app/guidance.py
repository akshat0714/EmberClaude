"""GuidanceBrain — calm, rule-based emergency voice assistant (v1).

Design rules, enforced by tests:
  * NEVER invents geometry. Every spatial statement is read out of the
    route engine's maneuvers and metrics.
  * NEVER promises safety. Banned phrasing ("guaranteed safe", "ignore
    officials", ...) is structurally absent; every response carries an
    official-orders reminder.
  * Deterministic and offline. The intent matcher + templates can be
    swapped for a real LLM later behind the same respond() contract —
    the LLM would only be allowed to paraphrase these same engine facts.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from . import geo
from .models import (
    GuidanceAction,
    GuidanceRequest,
    GuidanceResponse,
    RouteRecommendation,
)
from .state import ScenarioState

SAFETY_LINES = [
    "Follow official evacuation orders and emergency personnel.",
    "If emergency personnel are present, follow their official directions over mine.",
    "This is simulation-backed guidance — official evacuation orders come first.",
]

# Ordered: first match wins. "what if" hypotheticals checked before real reports.
INTENT_PATTERNS: List[Tuple[str, List[str]]] = [
    ("hypothetical_missed_turn", [r"what (if|happens if).*(miss|wrong turn)"]),
    ("visibility_lost", [r"can.?t see", r"cannot see", r"bright orange", r"\borange\b",
                         r"smoke ahead", r"low visibility", r"it'?s all smoke"]),
    ("missed_turn", [r"missed (the )?turn", r"miss(ed)? my turn", r"went past"]),
    ("road_blocked", [r"blocked", r"road.*closed", r"tree down", r"can.?t get through"]),
    ("repeat", [r"\brepeat\b", r"say (that )?again", r"what was that"]),
    ("am_i_safe", [r"am i safe", r"safe yet", r"are we safe", r"out of danger"]),
    ("keep_going", [r"keep going", r"should i (keep|continue)", r"continue\??$"]),
    ("where_do_i_go", [r"where (do|should) i go", r"where to", r"which way",
                       r"help me (get|leave)", r"how do i (get out|leave|evacuate)"]),
    ("status", [r"\bstatus\b", r"what.?s happening", r"situation"]),
]


def detect_intent(text: str) -> str:
    t = text.lower().strip()
    for intent, patterns in INTENT_PATTERNS:
        for p in patterns:
            if re.search(p, t):
                return intent
    return "general"


def _fmt_feet(meters: float) -> str:
    feet = meters * 3.28084
    if feet < 1000:
        return f"{int(round(feet / 50.0) * 50) or 50} feet"
    return f"{meters / 1609.34:.1f} miles"


def _safety_line(seed: int) -> str:
    return SAFETY_LINES[seed % len(SAFETY_LINES)]


def _route_summary(state: ScenarioState, lead_in: str = "") -> str:
    status = state._status_result()
    route = state.active_route
    if route is None:
        return "I do not have a computed route yet. Ask me 'where do I go?' to generate one."
    bits = []
    if lead_in:
        bits.append(lead_in)
    if status.arrived:
        bits.append("You have reached the simulated lower-risk zone.")
    else:
        if status.nextManeuver is not None:
            bits.append(f"In {_fmt_feet(status.distanceToManeuverMeters)}, "
                        f"{_lower(status.nextManeuver.instruction)}")
        bits.append(f"About {_fmt_feet(status.remainingDistanceMeters)} remain on the blue route, "
                    f"with a ~{status.remainingBufferMinutes:.0f}-minute modeled fire buffer.")
    return " ".join(bits)


def _lower(instruction: str) -> str:
    # "In 300 feet, turn right onto X" -> "turn right onto X" for nesting in speech.
    s = re.sub(r"^in [\w\.\s]+?, ", "", instruction, flags=re.IGNORECASE)
    return s[0].lower() + s[1:] if s and not s.startswith(("U-", "Make a U")) else s


def respond(req: GuidanceRequest, state: ScenarioState) -> GuidanceResponse:
    intent = detect_intent(req.text)
    if req.position is not None:
        state.user.lon, state.user.lat = req.position[0], req.position[1]
    state.user.minute = max(state.user.minute, req.minute)
    seed = len(req.text)

    actions: List[GuidanceAction] = []
    rec: Optional[RouteRecommendation] = None
    rerouted = False

    if intent == "where_do_i_go" or (intent == "general" and state.active_route is None):
        rec = state.recommend(minute=req.minute)
        best = next(c for c in rec.candidates if c.routeId == rec.recommendedRouteId)
        first_moves = " Then ".join(_lower(m.instruction) + "." for m in best.maneuvers[1:3])
        dest_part = f" toward {rec.destination.name}" if rec.destination else ""
        live_part = (" Directions are live Google Maps data."
                     if rec.source == "google_directions" else "")
        text = (f"Based on this simulation, follow the blue route: {best.name}{dest_part}. "
                f"{best.maneuvers[0].instruction}. {first_moves} "
                f"It scored best across modeled fire buffer (~{best.fireArrivalBufferMinutes:.0f} min), "
                f"smoke exposure ({best.smokeExposureScore:.0f}/100) and travel time, with "
                f"{best.confidence:.0%} route confidence.{live_part} {_safety_line(seed)}")
        actions.append(GuidanceAction(type="reroute", detail=best.routeId))
        rerouted = True

    elif intent == "visibility_lost":
        state.report_visibility_lost()
        rb = state.conditions.reportedBlockNear
        actions.append(GuidanceAction(
            type="set_visibility_lost",
            detail=f'{{"center": [{rb[0]:.6f}, {rb[1]:.6f}], "radiusM": 380}}' if rb else ""))
        rec = state.recommend(minute=req.minute, reroute=True)
        best = next(c for c in rec.candidates if c.routeId == rec.recommendedRouteId)
        text = (f"Understood — visibility risk increased. I am weighting smoke-heavy segments "
                f"against you and re-routing now. {best.maneuvers[0].instruction}. "
                f"Then {_lower(best.maneuvers[1].instruction) if len(best.maneuvers) > 1 else 'continue'}. "
                f"If you cannot drive safely, stop clear of the roadway with lights on. {_safety_line(seed)}")
        actions.append(GuidanceAction(type="reroute", detail=best.routeId))
        rerouted = True

    elif intent == "missed_turn":
        state.deviate("missed_turn")
        actions.append(GuidanceAction(type="deviate_user", detail="missed_turn"))
        rec = state.recommend(minute=req.minute, reroute=True)
        best = next(c for c in rec.candidates if c.routeId == rec.recommendedRouteId)
        text = (f"No problem — re-routing from your current position. "
                f"{best.maneuvers[0].instruction}. "
                f"{best.maneuvers[1].instruction + '.' if len(best.maneuvers) > 1 else ''} "
                f"The previous path is no longer optimal. {_safety_line(seed)}")
        actions.append(GuidanceAction(type="reroute", detail=best.routeId))
        rerouted = True

    elif intent == "road_blocked":
        state.deviate("blocked")
        actions.append(GuidanceAction(type="close_road", detail="reported_block_ahead"))
        rec = state.recommend(minute=req.minute, reroute=True)
        best = next(c for c in rec.candidates if c.routeId == rec.recommendedRouteId)
        text = (f"Thanks — I marked that segment as blocked in the simulation and re-routed. "
                f"{best.maneuvers[0].instruction}. Do not drive around barricades. {_safety_line(seed)}")
        actions.append(GuidanceAction(type="reroute", detail=best.routeId))
        rerouted = True

    elif intent == "repeat":
        text = f"{_route_summary(state, 'Repeating your current guidance.')} {_safety_line(seed)}"

    elif intent == "am_i_safe":
        status = state._status_result()
        if status.arrived:
            text = ("You have reached the simulated lower-risk zone. Based on current scenario inputs "
                    f"the modeled fire buffer here is ~{status.remainingBufferMinutes:.0f} minutes. "
                    f"Stay alert and {_safety_line(seed).lower()}")
            actions.append(GuidanceAction(type="arrived"))
        else:
            text = (f"Not yet — you are still inside the modeled risk area. "
                    f"{_route_summary(state)} I will keep updating as you move. {_safety_line(seed)}")

    elif intent == "keep_going":
        status = state._status_result()
        if status.remainingBufferMinutes >= 8 or status.arrived:
            text = (f"Yes — based on current scenario inputs the blue route is still the lowest "
                    f"modeled-risk option. {_route_summary(state)} {_safety_line(seed)}")
        else:
            rec = state.recommend(minute=req.minute, reroute=True)
            best = next(c for c in rec.candidates if c.routeId == rec.recommendedRouteId)
            text = (f"The modeled buffer tightened, so I re-checked. Recommended now: {best.name}. "
                    f"{best.maneuvers[0].instruction}. {_safety_line(seed)}")
            actions.append(GuidanceAction(type="reroute", detail=best.routeId))
            rerouted = True

    elif intent == "hypothetical_missed_turn":
        text = ("If you miss a turn, keep driving — do not stop in the roadway. I will detect the "
                "deviation, re-route from your live position, and read out the next safe maneuver. "
                f"{_safety_line(seed)}")

    elif intent == "status":
        sim = state.ensure_sim()
        frame = max((m for m in sim.minutes if m <= req.minute), default=0)
        n_cells = len(sim.fireCellsByMinute.get(str(frame), []))
        text = (f"Scenario minute {req.minute:.0f}: {n_cells} modeled active fire cells, wind "
                f"{sim.params.windSpeedMph:.0f} miles per hour from the northeast. "
                f"{_route_summary(state)} {_safety_line(seed)}")

    else:
        text = ("I can guide you along the lowest modeled-risk route in this simulation. Try: "
                "'Where do I go?', 'I can't see ahead', 'I missed the turn', or 'Am I safe yet?'. "
                f"{_safety_line(seed)}")

    return GuidanceResponse(
        intent=intent, transcriptText=text, speechText=text, actions=actions,
        rerouted=rerouted, recommendation=rec, userPosition=state.user)
